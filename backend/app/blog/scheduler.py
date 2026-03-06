"""
Blog Scheduler - Background task that auto-generates blog posts on schedule.
Runs hourly, checks if it's time to generate, respects daily limits.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.database import get_db

logger = logging.getLogger(__name__)


async def get_schedule() -> dict:
    """Get current schedule config"""
    db = await get_db()
    row = await db.fetchrow("SELECT * FROM blog_schedule WHERE id = 1")
    if not row:
        await db.execute("INSERT INTO blog_schedule (id) VALUES (1) ON CONFLICT DO NOTHING")
        row = await db.fetchrow("SELECT * FROM blog_schedule WHERE id = 1")
    return dict(row)


async def update_schedule(updates: dict) -> dict:
    """Update schedule config"""
    db = await get_db()
    allowed = ['enabled', 'posts_per_day', 'publish_hour', 'auto_publish']
    sets = []
    values = []
    idx = 1
    for key, val in updates.items():
        if key in allowed:
            sets.append(f"{key} = ${idx}")
            values.append(val)
            idx += 1
    if not sets:
        return await get_schedule()
    sets.append(f"updated_at = ${idx}")
    values.append(datetime.now(timezone.utc))
    query = f"UPDATE blog_schedule SET {', '.join(sets)} WHERE id = 1 RETURNING *"
    row = await db.fetchrow(query, *values)
    return dict(row)


async def _run_scheduled_generation():
    """Generate posts if schedule conditions are met"""
    from app.blog.service import generate_blog_post

    schedule = await get_schedule()
    if not schedule['enabled']:
        return

    now = datetime.now(timezone.utc)
    current_hour = now.hour

    # Check if it's the right hour to generate
    if current_hour != schedule['publish_hour']:
        return

    # Check if already ran today
    last_run = schedule.get('last_run_at')
    if last_run and last_run.date() == now.date():
        return

    # Generate posts
    posts_to_generate = schedule['posts_per_day']
    auto_publish = schedule['auto_publish']
    generated = 0

    logger.info(f"Blog scheduler: generating {posts_to_generate} posts (auto_publish={auto_publish})")

    for i in range(posts_to_generate):
        try:
            result = await generate_blog_post(auto_publish=auto_publish)
            if "error" in result:
                logger.warning(f"Blog scheduler: {result['error']}")
                break
            generated += 1
            logger.info(f"Blog scheduler: generated '{result['title']}' ({result['status']})")
        except Exception as e:
            logger.error(f"Blog scheduler error on post {i+1}: {e}")
            break

    # Update last run
    db = await get_db()
    await db.execute(
        "UPDATE blog_schedule SET last_run_at = $1, posts_generated_today = $2 WHERE id = 1",
        now, generated
    )
    logger.info(f"Blog scheduler: done. Generated {generated}/{posts_to_generate} posts.")


async def blog_scheduler_loop():
    """Background loop - checks every 30 minutes"""
    await asyncio.sleep(10)  # Wait for app startup
    logger.info("Blog scheduler started")
    while True:
        try:
            await _run_scheduled_generation()
        except Exception as e:
            logger.error(f"Blog scheduler loop error: {e}")
        await asyncio.sleep(1800)  # Check every 30 minutes
