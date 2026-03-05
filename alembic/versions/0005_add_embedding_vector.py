"""Add pgvector embedding_vec column and backfill from JSONB

Revision ID: 0005_add_embedding_vector
Revises: 0004_expand_mvm_schema
Create Date: 2026-03-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0005_add_embedding_vector"
down_revision = "0004_expand_mvm_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure vector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Add vector column (1024 dims = multilingual-e5-large)
    op.execute("ALTER TABLE datasets ADD COLUMN IF NOT EXISTS embedding_vec vector(1024);")

    # Backfill from JSONB: cast text representation to vector
    # The JSONB embedding is stored as a JSON array of floats
    op.execute("""
        UPDATE datasets
        SET embedding_vec = embedding::text::vector
        WHERE embedding IS NOT NULL
          AND jsonb_array_length(embedding) = 1024
          AND embedding_vec IS NULL;
    """)

    # HNSW index for fast approximate nearest-neighbor search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_datasets_embedding_vec_hnsw
        ON datasets USING hnsw (embedding_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # Also add a GIN index on title+description for keyword fallback
    # Note: array_to_string is STABLE not IMMUTABLE in PostgreSQL, so it cannot
    # be used in GENERATED ALWAYS columns. Use title+description+publisher only.
    op.execute("""
        ALTER TABLE datasets
        ADD COLUMN IF NOT EXISTS fts_doc tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(title, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(publisher, '')
            )
        ) STORED;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_datasets_fts
        ON datasets USING gin(fts_doc);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_datasets_fts;")
    op.execute("ALTER TABLE datasets DROP COLUMN IF EXISTS fts_doc;")
    op.execute("DROP INDEX IF EXISTS idx_datasets_embedding_vec_hnsw;")
    op.execute("ALTER TABLE datasets DROP COLUMN IF EXISTS embedding_vec;")
