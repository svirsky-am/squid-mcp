from wb_reporter.cards import apply_changes, build_duplicate_payload, build_update_payload

CARD = {
    "nmID": 123,
    "imtID": 456,
    "vendorCode": "OLD-1",
    "brand": "Brand",
    "title": "Старое название",
    "characteristics": [
        {"name": "Состав", "value": ["хлопок"]},
        {"name": "Цвет", "value": []},
    ],
}


def test_apply_changes_attributes():
    new = apply_changes(CARD, {"Состав": "шерсть", "title": "Новое"})
    assert new["title"] == "Новое"
    assert new["characteristics"][0]["value"] == ["шерсть"]
    # пустые характеристики вычищаются
    assert all(c["name"] != "Цвет" for c in new["characteristics"])
    # исходная карточка не мутировала
    assert CARD["title"] == "Старое название"


def test_duplicate_payload_strips_server_fields():
    payload = build_duplicate_payload(CARD, {"vendorCode": "NEW-1", "title": "Копия"})
    card = payload["cards"][0]
    assert card["vendorCode"] == "NEW-1"
    assert "nmID" not in card
    assert "imtID" not in card


def test_update_payload_keeps_nm_id():
    payload = build_update_payload(CARD, {"Состав": "лён"})
    assert payload["cards"][0]["nmID"] == 123
