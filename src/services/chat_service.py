"""
Chat service - manages per-user chat history, search, and export.
"""

import json
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from Data.models import Chat, Message

EXPORT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "exports")
)


def create_chat(
    db: Session,
    user_id: str,
    title: str = "New Chat",
    model: str | None = None,
) -> dict:
    """Create a new chat for a user."""
    from services.llm_service import get_default_model

    resolved_model = model or get_default_model() or ""
    chat = Chat(user_id=user_id, title=title, model=resolved_model)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _chat_to_dict(chat)


def list_chats(db: Session, user_id: str) -> list:
    """List all chats for a user, newest first."""
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user_id)
        .order_by(Chat.updated_at.desc())
        .all()
    )
    return [_chat_to_dict(c) for c in chats]


def get_chat(db: Session, chat_id: str, user_id: str) -> dict | None:
    """Get a single chat with all its messages."""
    chat = db.query(Chat).filter(Chat.id == chat_id,
                                 Chat.user_id == user_id).first()
    if not chat:
        return None
    result = _chat_to_dict(chat)
    result["messages"] = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "thinking": m.thinking,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in chat.messages
    ]
    return result


def delete_chat(db: Session, chat_id: str, user_id: str) -> bool:
    """Delete a chat and all its messages."""
    chat = db.query(Chat).filter(Chat.id == chat_id,
                                 Chat.user_id == user_id).first()
    if not chat:
        return False
    db.delete(chat)
    db.commit()
    return True


def rename_chat(db: Session, chat_id: str,
                user_id: str, title: str) -> dict | None:
    """Rename a chat."""
    chat = db.query(Chat).filter(Chat.id == chat_id,
                                 Chat.user_id == user_id).first()
    if not chat:
        return None
    chat.title = title
    db.commit()
    db.refresh(chat)
    return _chat_to_dict(chat)


def add_message(
    db: Session, chat_id: str, role: str, content: str, thinking: str = None
) -> Message:
    """Add a message to a chat and update the chat's updated_at."""
    msg = Message(chat_id=chat_id, role=role,
                  content=content, thinking=thinking)
    db.add(msg)
    # Update chat's updated_at
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat:
        chat.updated_at = datetime.now(timezone.utc)
        # Auto-title: use first user message (truncated) if still default
        if chat.title == "New Chat" and role == "user":
            chat.title = content[:80] + ("..." if len(content) > 80 else "")
    db.commit()
    db.refresh(msg)
    return msg


def get_chat_messages(db: Session, chat_id: str) -> list:
    """Get all messages for a chat in order."""
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )
    return [
        {"role": m.role, "content": m.content,
         "thinking": m.thinking} for m in messages
    ]


def search_chats(db: Session, user_id: str, query: str) -> list:
    """Search through a user's chats by message content."""
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user_id)
        .join(Message)
        .filter(Message.content.ilike(f"%{query}%"))
        .distinct()
        .order_by(Chat.updated_at.desc())
        .all()
    )
    results = []
    for chat in chats:
        chat_dict = _chat_to_dict(chat)
        # Include matching message snippets
        matching_msgs = (
            db.query(Message)
            .filter(Message.chat_id == chat.id)
            .filter(Message.content.ilike(f"%{query}%"))
            .all()
        )
        chat_dict["matching_messages"] = [
            {
                "role": m.role,
                "content": m.content[:200] +
                ("..." if len(m.content) > 200 else ""),
                "created_at": m.created_at.isoformat()
                if m.created_at else None,
            }
            for m in matching_msgs
        ]
        results.append(chat_dict)
    return results


def export_chat(
    db: Session, chat_id: str, user_id: str, fmt: str = "json"
) -> str | None:
    """
    Export a chat to a file. Returns the file path on success.
    Supported formats: json, txt, md
    """
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return None

    os.makedirs(EXPORT_DIR, exist_ok=True)
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_")
        else "_" for c in chat["title"]
    )[:50].strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{timestamp}.{fmt}"
    filepath = os.path.join(EXPORT_DIR, filename)

    messages = chat.get("messages", [])

    if fmt == "json":
        export_data = {
            "chat_id": chat["id"],
            "title": chat["title"],
            "model": chat["model"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "messages": messages,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    elif fmt == "md":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {chat['title']}\n\n")
            f.write(f"**Model:** {chat['model']}\n\n---\n\n")
            for m in messages:
                role_label = "User" if m["role"] == "user" else "Assistant"
                f.write(f"### {role_label}\n\n")
                if m.get("thinking"):
                    f.write(
                        f"<details>\n<summary>Thinking</summary>\n\n"
                        f"{m['thinking']}\n\n</details>\n\n"
                    )
                f.write(f"{m['content']}\n\n---\n\n")

    elif fmt == "txt":
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Chat: {chat['title']}\n")
            f.write(f"Model: {chat['model']}\n")
            f.write("=" * 60 + "\n\n")
            for m in messages:
                role_label = "User" if m["role"] == "user" else "Assistant"
                f.write(f"[{role_label}]\n")
                if m.get("thinking"):
                    f.write(f"[Thinking]: {m['thinking']}\n\n")
                f.write(f"{m['content']}\n\n")
                f.write("-" * 40 + "\n\n")
    else:
        return None

    return filepath


def _chat_to_dict(chat: Chat) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }
