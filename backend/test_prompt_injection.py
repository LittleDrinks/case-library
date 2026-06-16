#!/usr/bin/env python3
"""Compatibility wrapper; canonical test lives in backend/tests/unit/."""

from tests.unit.test_prompt_injection import get_mongo_client, main_test, os

if __name__ == "__main__":
    try:
        main_test()
    finally:
        get_mongo_client().drop_database(os.environ["MONGODB_DB_NAME"])
