"""Default catalog for a new database. Hosts add their own roles on top."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.models import Role, UserTier

DEFAULT_ROLE = "user"
DEFAULT_TIER = "free"
PRO_TIER = "pro"


async def seed_defaults(db: AsyncSession) -> None:
    role = await db.get(Role, DEFAULT_ROLE)
    if role is None:
        db.add(
            Role(
                code=DEFAULT_ROLE,
                name="用户",
                sort_order=0,
                is_default=True,
                allow_register=True,
            )
        )
    tier = await db.get(UserTier, DEFAULT_TIER)
    if tier is None:
        db.add(
            UserTier(
                code=DEFAULT_TIER,
                name="免费版",
                sort_order=0,
                badge_color="#8c8c8c",
                is_default=True,
            )
        )
    pro = await db.get(UserTier, PRO_TIER)
    if pro is None:
        db.add(UserTier(code=PRO_TIER, name="Pro", sort_order=10, badge_color="#1677ff", is_default=False))
    await db.commit()


async def default_role(db: AsyncSession) -> Role:
    result = await db.execute(select(Role).where(Role.is_default.is_(True)).limit(1))
    row = result.scalars().first()
    if row is None:
        await seed_defaults(db)
        result = await db.execute(select(Role).where(Role.is_default.is_(True)).limit(1))
        row = result.scalars().first()
    return row


async def default_tier(db: AsyncSession) -> UserTier:
    result = await db.execute(select(UserTier).where(UserTier.is_default.is_(True)).limit(1))
    row = result.scalars().first()
    if row is None:
        await seed_defaults(db)
        result = await db.execute(select(UserTier).where(UserTier.is_default.is_(True)).limit(1))
        row = result.scalars().first()
    return row
