from src.gui.main_window import MainWindow


def test_user_manual_opens_online_page_in_default_browser(monkeypatch) -> None:
    opened_urls = []
    monkeypatch.setattr("src.gui.main_window.webbrowser.open_new_tab", opened_urls.append)

    MainWindow.__new__(MainWindow)._open_user_manual()

    assert opened_urls == ["https://weijiayue19.github.io/project6_404foundOCR/user_manual/"]
