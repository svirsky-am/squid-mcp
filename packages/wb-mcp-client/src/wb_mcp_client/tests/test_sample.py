def test_basic_math():
    assert 1 + 1 == 2

def test_import_package():
    # Проверка, что сам пакет корректно импортируется в workspace
    import wb_mcp_client
    assert wb_mcp_client is not None