"""Direct Oracle connection smoke test; does not require MCP server to run."""
from oracle_db import test_select

if __name__ == "__main__":
    result = test_select()
    print(result)
    if result.get("status") != "MCP_OK":
        raise SystemExit("Oracle SELECT check failed")
    print("ORACLE_SELECT_PASS")
