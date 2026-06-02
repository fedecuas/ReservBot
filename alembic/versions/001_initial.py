"""Initial schema
Revision ID: 001_initial
Revises:
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('businesses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phone_number_id', sa.String(64), nullable=False),
        sa.Column('waba_id', sa.String(64), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('category', sa.String(64), nullable=True),
        sa.Column('timezone', sa.String(64), server_default='America/Mexico_City'),
        sa.Column('language', sa.String(8), server_default='es'),
        sa.Column('bot_name', sa.String(64), server_default='Valentina'),
        sa.Column('bot_active', sa.Boolean(), server_default='true'),
        sa.Column('welcome_message', sa.Text(), nullable=True),
        sa.Column('subscription_plan', sa.String(32), server_default='starter'),
        sa.Column('subscription_status', sa.String(32), server_default='active'),
        sa.Column('monthly_price', sa.Numeric(10,2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_businesses_phone_number_id', 'businesses', ['phone_number_id'], unique=True)
    op.create_table('services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration_min', sa.Integer(), server_default='30'),
        sa.Column('price', sa.Numeric(10,2), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true'),
        sa.Column('list_item_id', sa.String(24), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('business_hours',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), server_default='false'),
        sa.Column('start_time', sa.String(5), server_default='09:00'),
        sa.Column('end_time', sa.String(5), server_default='19:00'),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id']),
        sa.PrimaryKeyConstraint('id'),
    )

def downgrade():
    op.drop_table('business_hours')
    op.drop_table('services')
    op.drop_table('businesses')
