#!/usr/bin/env python3
"""Compatibility wrapper; canonical test lives in backend/tests/integration/."""

from tests.integration.test_submit_flow import get_mongo_client, main_test, os

if __name__ == "__main__":
    try:
        main_test()
        print("submit flow checks passed")
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
