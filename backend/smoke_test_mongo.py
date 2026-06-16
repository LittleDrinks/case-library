#!/usr/bin/env python3
"""Compatibility wrapper; canonical smoke script lives in backend/tests/smoke/."""

from tests.smoke.smoke_test_mongo import main

if __name__ == "__main__":
    main()
