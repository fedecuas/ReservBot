"""
Alembic migration 002 — agrega tablas: professionals, appointments, conversations
y columna owner_phone en businesses.
"""
from alembic import op
import sqlalchemy as sa


revision = '002_add_professionals_appointments_conversations'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # ── owner_phone en businesses ────────────────────────────────
    op.add_column('businesses', sa.Column('owner_phone', sa.String(20), nullable=True))

    # ── professionals ────────────────────────────────────────────
    op.create_table(
        'professionals',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('calendar_id', sa.String(255), nullable=True),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('accepts_walkins', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )

    # ── appointments ─────────────────────────────────────────────
    op.create_table(
        'appointments',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('professional_id', sa.Integer(), sa.ForeignKey('professionals.id', ondelete='SET NULL'), nullable=True),
        sa.Column('client_name', sa.String(128), nullable=False),
        sa.Column('client_phone', sa.String(20), nullable=False, index=True),
        sa.Column('service_name', sa.String(128), nullable=False),
        sa.Column('appointment_date', sa.String(10), nullable=False),
        sa.Column('appointment_time', sa.String(5), nullable=False),
        sa.Column('duration_min', sa.Integer(), default=30),
        sa.Column('calendar_event_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), default='confirmed'),
        sa.Column('reminder_sent', sa.Boolean(), default=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── conversations ─────────────────────────────────────────────
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('client_phone', sa.String(20), nullable=False, index=True),
        sa.Column('client_name', sa.String(128), nullable=True),
        sa.Column('messages', sa.Text(), nullable=True),
        sa.Column('intent_log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('conversations')
    op.drop_table('appointments')
    op.drop_table('professionals')
    op.drop_column('businesses', 'owner_phone')
