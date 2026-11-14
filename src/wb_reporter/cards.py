"""Работа с карточками товаров: нормализация, правка и дублирование.

Получение:  POST /content/v2/get/cards/list
Правка:     POST /content/v2/cards/update   (существующие карточки)
Создание:   POST /content/v2/cards/upload    (дубликат как новый товар)

Внимание: /cards/update правит атрибуты существующих карточек и не создаёт
новые. Поэтому «дубликат» собирается в build_duplicate_payload и уходит
в upload_cards (host зависит от USE_SANDBOX_UPDATE).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Поля, которые WB сам расставляет и которые нельзя тащить в новую карточку
AUTO_FIELDS = ("nmID", "imtID", "createdAt", "updatedAt", "mediaFiles", "productVersions")


def apply_changes(card: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Применяет изменения к копии карточки.

    Ключи `title`, `brand`, `vendorCode` меняют соответствующие поля.
    Любой другой ключ ищется по name среди characteristics и меняет value.
    """
    new = copy.deepcopy(card)
    characteristics = new.get("characteristics") or []
    for key, value in changes.items():
        if key in ("title", "brand", "vendorCode"):
            new[key] = value
            continue
        matched = False
        for c in characteristics:
            if isinstance(c, dict) and c.get("name") == key:
                c["value"] = value if isinstance(value, list) else [value]
                matched = True
        if not matched:
            logger.warning("Характеристика '%s' не найдена в карточке — пропущена", key)
    # WB с 2026 года предупреждает на пустые value в characteristics
    new["characteristics"] = [
        c for c in characteristics
        if not (isinstance(c, dict) and (c.get("value") in ("", None) or c.get("value") == []))
    ]
    return new


def build_update_payload(card: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Payload для /content/v2/cards/update: правка атрибутов существующей карточки."""
    return {"cards": [apply_changes(card, changes)]}


def build_duplicate_payload(card: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Payload для /content/v2/cards/upload: копия карточки с изменёнными атрибутами.

    Убирает серверные поля (nmID и т. п.) — иначе WB отклонит запрос.
    Артикул (vendorCode) стоит менять обязательно, иначе получите дубликат
    существующего артикула.
    """
    new = apply_changes(card, changes)
    for field in AUTO_FIELDS:
        new.pop(field, None)
    return {"cards": [new]}
