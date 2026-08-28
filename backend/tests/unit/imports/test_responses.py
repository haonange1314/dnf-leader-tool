from app.api.v1.routes.imports import _xlsx_response


def test_xlsx_response_encodes_chinese_filename() -> None:
    response = _xlsx_response(b"workbook", "DNF角色导入模板.xlsx")

    assert response.headers["content-disposition"] == (
        'attachment; filename="DNF.xlsx"; '
        "filename*=UTF-8''DNF%E8%A7%92%E8%89%B2%E5%AF%BC%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"
    )
    assert response.media_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
