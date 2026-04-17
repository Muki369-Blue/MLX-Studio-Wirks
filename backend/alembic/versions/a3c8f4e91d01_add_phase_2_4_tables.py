"""add phase 2-4 tables: campaigns, tasks, persona_memory, agent_runs, metrics

Revision ID: a3c8f4e91d01
Revises: 5566ad86f45c
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c8f4e91d01'
down_revision = '5566ad86f45c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Phase 2: Campaign + Orchestration ────────────────────────────
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('personas.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), server_default='draft'),
        sa.Column('total_days', sa.Integer(), server_default='4'),
        sa.Column('current_day', sa.Integer(), server_default='0'),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_campaigns_id', 'campaigns', ['id'])

    op.create_table(
        'campaign_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending'),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('generation_jobs.id'), nullable=True),
        sa.Column('depends_on', sa.JSON(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_campaign_tasks_id', 'campaign_tasks', ['id'])
    op.create_index('ix_campaign_tasks_campaign_id', 'campaign_tasks', ['campaign_id'])

    # ── Phase 3: Persona Memory + Agents ─────────────────────────────
    op.create_table(
        'persona_memory',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('personas.id'), nullable=False),
        sa.Column('partition', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_persona_memory_id', 'persona_memory', ['id'])
    op.create_index('ix_persona_memory_persona_id', 'persona_memory', ['persona_id'])
    op.create_index('ix_persona_memory_lookup', 'persona_memory', ['persona_id', 'partition', 'key'], unique=True)

    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('agent_type', sa.String(), nullable=False),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('personas.id'), nullable=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=True),
        sa.Column('input_payload', sa.JSON(), nullable=True),
        sa.Column('output_payload', sa.JSON(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default='running'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_agent_runs_id', 'agent_runs', ['id'])
    op.create_index('ix_agent_runs_agent_type', 'agent_runs', ['agent_type'])

    # ── Phase 4: Extended Analytics ──────────────────────────────────
    op.create_table(
        'content_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('contents.id'), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('views', sa.Integer(), server_default='0'),
        sa.Column('likes', sa.Integer(), server_default='0'),
        sa.Column('comments', sa.Integer(), server_default='0'),
        sa.Column('tips', sa.Float(), server_default='0.0'),
        sa.Column('unlocks', sa.Integer(), server_default='0'),
        sa.Column('saves', sa.Integer(), server_default='0'),
        sa.Column('collected_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_content_metrics_id', 'content_metrics', ['id'])
    op.create_index('ix_content_metrics_content_id', 'content_metrics', ['content_id'])

    op.create_table(
        'persona_metrics_daily',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('personas.id'), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('new_subscribers', sa.Integer(), server_default='0'),
        sa.Column('churned_subscribers', sa.Integer(), server_default='0'),
        sa.Column('revenue', sa.Float(), server_default='0.0'),
        sa.Column('tips', sa.Float(), server_default='0.0'),
        sa.Column('messages_received', sa.Integer(), server_default='0'),
        sa.Column('messages_sent', sa.Integer(), server_default='0'),
        sa.Column('content_posted', sa.Integer(), server_default='0'),
        sa.Column('avg_engagement_rate', sa.Float(), server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_persona_metrics_daily_id', 'persona_metrics_daily', ['id'])
    op.create_index('ix_persona_metrics_daily_lookup', 'persona_metrics_daily', ['persona_id', 'date', 'platform'], unique=True)

    op.create_table(
        'campaign_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('content_produced', sa.Integer(), server_default='0'),
        sa.Column('content_approved', sa.Integer(), server_default='0'),
        sa.Column('content_rejected', sa.Integer(), server_default='0'),
        sa.Column('content_posted', sa.Integer(), server_default='0'),
        sa.Column('revenue_attributed', sa.Float(), server_default='0.0'),
        sa.Column('new_subscribers', sa.Integer(), server_default='0'),
        sa.Column('total_engagement', sa.Integer(), server_default='0'),
        sa.Column('collected_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_campaign_metrics_id', 'campaign_metrics', ['id'])
    op.create_index('ix_campaign_metrics_campaign_id', 'campaign_metrics', ['campaign_id'])

    op.create_table(
        'caption_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('contents.id'), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('caption_text', sa.Text(), nullable=False),
        sa.Column('hashtags', sa.Text(), nullable=True),
        sa.Column('variant', sa.String(), server_default='A'),
        sa.Column('impressions', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('engagement_rate', sa.Float(), server_default='0.0'),
        sa.Column('collected_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_caption_metrics_id', 'caption_metrics', ['id'])
    op.create_index('ix_caption_metrics_content_id', 'caption_metrics', ['content_id'])

    op.create_table(
        'generation_cost_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('generation_jobs.id'), nullable=False),
        sa.Column('machine', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('estimated_cost_usd', sa.Float(), server_default='0.0'),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_generation_cost_metrics_id', 'generation_cost_metrics', ['id'])
    op.create_index('ix_generation_cost_metrics_job_id', 'generation_cost_metrics', ['job_id'])


def downgrade() -> None:
    op.drop_table('generation_cost_metrics')
    op.drop_table('caption_metrics')
    op.drop_table('campaign_metrics')
    op.drop_table('persona_metrics_daily')
    op.drop_table('content_metrics')
    op.drop_table('agent_runs')
    op.drop_table('persona_memory')
    op.drop_table('campaign_tasks')
    op.drop_table('campaigns')
