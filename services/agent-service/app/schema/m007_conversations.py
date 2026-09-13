"""Baseline migration copied from the established domain store; append new versions."""

def migrate(conn) -> None:
    conn.execute("""
        create table if not exists conversations (
            conversation_id text primary key,
            tenant_id text not null,
            owner_id text not null,
            revision integer not null default 0,
            summary text not null default '',
            summary_through integer not null default 0,
            model_calls integer not null default 0,
            tool_calls integer not null default 0,
            lease_id text,
            lease_until real not null default 0,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        )
    """)
    conn.execute("""
        create table if not exists conversation_turns (
            exchange_id text primary key,
            conversation_id text not null,
            turn integer not null,
            tenant_id text not null,
            owner_id text not null,
            question text not null,
            rewritten_question text not null,
            answer text not null,
            sources_json text not null,
            created_at text not null default current_timestamp,
            foreign key (conversation_id) references conversations(conversation_id),
            unique(conversation_id, turn)
        )
    """)
    conn.execute("create index if not exists idx_conversation_scope on conversations(tenant_id, owner_id)")
