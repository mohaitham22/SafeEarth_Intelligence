"""
Ad business logic.

list_active_ads   — used by GET /ads (public home-page source)
list_all_ads      — used by GET /admin/ads (includes inactive)
create_ad         — POST /admin/ads
update_ad         — PATCH /admin/ads/{id}
deactivate_ad     — DELETE /admin/ads/{id}  (soft delete)
upload_ad_image   — POST /admin/ads/{id}/image  (saves file, sets image_url)
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ad import Ad
from schemas.ad import AdCreate, AdUpdate

# Allowed MIME types for ad images
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Where uploaded images are stored (relative to backend root — main.py mounts this)
_STATIC_ADS_DIR = Path(__file__).resolve().parent.parent / "static" / "ads"


async def list_active_ads(db: AsyncSession) -> list[Ad]:
    """Return active ads, ordered by sort_order then newest first."""
    result = await db.execute(
        select(Ad)
        .where(Ad.is_active.is_(True))
        .order_by(Ad.sort_order.asc(), Ad.created_at.desc())
    )
    return list(result.scalars().all())


async def list_all_ads(db: AsyncSession) -> list[Ad]:
    """Return ALL ads (including inactive) for the admin Studio view."""
    result = await db.execute(
        select(Ad).order_by(Ad.sort_order.asc(), Ad.created_at.desc())
    )
    return list(result.scalars().all())


async def create_ad(db: AsyncSession, *, body: AdCreate) -> Ad:
    """Create a new ad and return it."""
    ad = Ad(
        id         = uuid.uuid4(),
        title      = body.title,
        body       = body.body,
        image_url  = body.image_url,
        link_url   = body.link_url,
        cta_label  = body.cta_label,
        sort_order = body.sort_order,
        is_active  = body.is_active,
    )
    db.add(ad)
    await db.commit()
    await db.refresh(ad)
    return ad


async def update_ad(db: AsyncSession, *, ad_id: UUID, body: AdUpdate) -> Ad:
    """Update any subset of ad fields. Returns the updated ad."""
    result = await db.execute(select(Ad).where(Ad.id == ad_id))
    ad     = result.scalar_one_or_none()
    if ad is None:
        raise HTTPException(status_code=404, detail="Ad not found.")

    if body.title      is not None: ad.title      = body.title
    if body.body       is not None: ad.body        = body.body
    if body.image_url  is not None: ad.image_url   = body.image_url
    if body.link_url   is not None: ad.link_url    = body.link_url
    if body.cta_label  is not None: ad.cta_label   = body.cta_label
    if body.sort_order is not None: ad.sort_order  = body.sort_order
    if body.is_active  is not None: ad.is_active   = body.is_active

    await db.commit()
    await db.refresh(ad)
    return ad


async def deactivate_ad(db: AsyncSession, *, ad_id: UUID) -> None:
    """Soft-delete an ad (sets is_active=False)."""
    result = await db.execute(select(Ad).where(Ad.id == ad_id))
    ad     = result.scalar_one_or_none()
    if ad is None:
        raise HTTPException(status_code=404, detail="Ad not found.")
    ad.is_active = False
    await db.commit()


async def upload_ad_image(
    db:     AsyncSession,
    *,
    ad_id:  UUID,
    upload: UploadFile,
    api_base_url: str,
) -> Ad:
    """Save an uploaded image to static/ads/, update the ad's image_url, return the ad.

    api_base_url is injected by the router (e.g. "https://api.safeearth.tech/api/v1")
    so the stored URL is absolute and works in the frontend without config knowledge here.
    The /static mount is at the app root, not under /api/v1, so we strip the path suffix.
    """
    result = await db.execute(select(Ad).where(Ad.id == ad_id))
    ad     = result.scalar_one_or_none()
    if ad is None:
        raise HTTPException(status_code=404, detail="Ad not found.")

    content_type = upload.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{content_type}'. Allowed: jpeg, png, webp, gif.",
        )

    _STATIC_ADS_DIR.mkdir(parents=True, exist_ok=True)

    original_name = (upload.filename or "image.jpg").replace(" ", "_")
    filename      = f"{ad_id}_{original_name}"
    dest          = _STATIC_ADS_DIR / filename

    contents = await upload.read()
    dest.write_bytes(contents)

    # Build the public URL: strip /api/v1 suffix if present so we get the root
    base = api_base_url.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    ad.image_url = f"{base}/static/ads/{filename}"

    await db.commit()
    await db.refresh(ad)
    return ad
