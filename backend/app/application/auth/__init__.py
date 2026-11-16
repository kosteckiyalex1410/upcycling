"""Authentication use cases (ADR-0003).

`sessions` is independent of how the user proved their identity; each login
method (currently `email_login`) verifies identity and then issues a session.
"""
