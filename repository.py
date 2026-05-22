import gspread

class TalkDB:
    def __init__(self, secret: dict, sh_name: str):
        self.gc      = gspread.service_account_from_dict(secret)
        self.sh_name = sh_name

    def _get_worksheet(self, tab_name: str) -> gspread.Worksheet:
        sh = self.gc.open(self.sh_name)
        return sh.worksheet(tab_name)

    def get_records(self, tab_name: str) -> list[dict]:
        return self._get_worksheet(tab_name).get_all_records()

    def append_row(self, tab_name: str, row: list) -> None:
        self._get_worksheet(tab_name).append_row(row)

    def clear_and_write(self, tab_name: str, rows: list[list]) -> None:
        ws = self._get_worksheet(tab_name)
        ws.clear()
        ws.append_rows(rows)