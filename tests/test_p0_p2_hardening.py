"""P0-P2 staged regression: replay, outbox, retry, revocation and scoped MCP."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_bridge as bridge
import codex_events as events
import codex_recovery
import instruction_store as store
import instruction_approvals
from windows_agent.event_outbox import EventOutbox


class IsolatedDatabase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        filename = str(Path(tmp.name) / "hardening.sqlite")
        patcher = patch.object(bridge.settings_store, "_connect",
                               side_effect=lambda: sqlite3.connect(filename))
        patcher.start()
        self.addCleanup(patcher.stop)


class ReplayTests(IsolatedDatabase):
    def setUp(self):
        super().setUp()
        self.task, self.agent, self.lease = "a" * 32, "win-dev-01", "b" * 48
        db = bridge._connect()
        db.execute("""INSERT INTO codex_agent_jobs
            (id,project,repository,branch,expected_sha,kind,instructions,
             state,actor,created_at,claimed_at,agent_id,lease_token_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.task,"LKH","gyangho/LKH_MCP","main","e"*40,"verify","",
             "running","test",1,bridge._now(),self.agent,
             hashlib.sha256(self.lease.encode()).hexdigest()))
        db.commit()
        db.close()

    def test_replay_is_idempotent_and_conflicts_denied(self):
        first = [{"seq":1,"type":"started","phase":"codex"}]
        self.assertEqual(events.append(self.task,self.agent,self.lease,first)["accepted"],1)
        self.assertEqual(events.append(self.task,self.agent,self.lease,first)["accepted"],0)
        with self.assertRaises(ValueError):
            events.append(self.task,self.agent,self.lease,[dict(first[0],type="finished")])
        with self.assertRaises(ValueError):
            events.append(self.task,self.agent,self.lease,first+first)


class RetryTests(IsolatedDatabase):
    def setUp(self):
        super().setUp()
        self.task = "c"*32
        self.allow = patch.object(bridge, "_allowed", return_value={"LKH":"gyangho/LKH_MCP"})
        self.allow.start(); self.addCleanup(self.allow.stop)
        self.enabled = patch.object(bridge, "_enabled")
        self.enabled.start(); self.addCleanup(self.enabled.stop)
        db = bridge._connect()
        db.execute("""INSERT INTO codex_agent_jobs
             (id,project,repository,branch,expected_sha,kind,instructions,state,actor,created_at)
             VALUES(?,?,?,?,?,?,?,?,?,?)""",
             (self.task,"LKH","gyangho/LKH_MCP","main","d"*40,"verify","","failed","tester",1))
        db.commit(); db.close()

    def test_idempotent_retry_does_not_mutate_sha(self):
        a = codex_recovery.retry_failed(self.task,"admin")
        b = codex_recovery.retry_failed(self.task,"admin")
        self.assertEqual(a["id"],b["id"])
        self.assertTrue(b["reused"])
        self.assertEqual(bridge.get_task(a["id"])["expected_sha"],"d"*40)


class InstructionTests(IsolatedDatabase):
    def test_revoke_published_body_and_keep_history(self):
        item=store.create("safe","project","ITAM","rule","admin")
        store.publish(item["id"],1,"admin")
        store.revoke(item["id"],1,"admin")
        with self.assertRaises(ValueError):
            store.get_entry(item["id"])
        self.assertEqual(store.history(item["id"])["versions"][0]["body"],"rule")
        self.assertEqual(store.list_entries()["instructions"],[])

    def test_self_review_rejected(self):
        item=store.create("policy","global","","safe","alice")
        instruction_approvals.request_review(item["id"],1,"alice")
        with self.assertRaises(PermissionError):
            instruction_approvals.approve_review(item["id"],1,"alice")
        instruction_approvals.approve_review(item["id"],1,"bob")
        self.assertTrue(instruction_approvals.is_approved(item["id"],1))


class BufferTests(unittest.TestCase):
    def test_retry_and_safe_metadata_only(self):
        deliveries=[]
        fail=[True]
        def send(batch):
            if fail[0]:
                fail[0]=False
                raise OSError("offline")
            deliveries.extend(batch)
        clock=[0.0]
        buf=EventOutbox(send,clock=lambda:clock[0],capacity=3,batch_size=3)
        for kind in ("started","turn_started","turn_completed"):
            buf.emit(kind,"codex")
        self.assertEqual(buf.pending,3)
        self.assertEqual(buf.flush(),3)
        self.assertEqual([x["seq"] for x in deliveries],[1,2,3])
        with self.assertRaises(ValueError):
            buf.emit("some command with secret","codex")


if __name__ == "__main__":
    unittest.main()
