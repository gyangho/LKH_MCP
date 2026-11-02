"""Direct Oracle connection smoke test; does not require MCP server to run."""
from oracle_db import test_select

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("connection_id")
    result = test_select(parser.parse_args().connection_id)
    print(result)
    if result.get("status") != "MCP_OK":
        raise SystemExit("Oracle SELECT check failed")
    print("ORACLE_SELECT_PASS")
