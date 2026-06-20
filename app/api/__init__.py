"""
API Routes Package
Aggregates all API route modules.
"""

# This file should be saved as app/api/__init__.py

from . import auth, bookmarks, chat, companies, conversations, documents, insights, messages, users

__all__ = [
    "auth",
    "users",
    "companies",
    "documents",
    "conversations",
    "messages",
    "bookmarks",
    "insights",
    "chat",
]