from ai_runtime.lab.menu import MenuItem, TerminalMenu


def make_menu(keys, *, clipboard=""):
    key_iter = iter(keys)
    return TerminalMenu(
        key_reader=lambda: next(key_iter),
        clipboard_reader=lambda: clipboard,
        interactive=True,
    )


def test_arrow_navigation_and_right_enter_selected_item(capsys):
    menu = make_menu(["down", "right"])

    selected = menu.choose(
        "主菜单",
        (MenuItem("1", "第一项"), MenuItem("2", "第二项")),
    )

    assert selected == "2"
    assert "↑↓ 选择" in capsys.readouterr().out


def test_number_enters_directly_and_left_returns(capsys):
    selected = make_menu(["2"]).choose(
        "主菜单",
        (MenuItem("1", "第一项"), MenuItem("2", "第二项")),
    )
    returned = make_menu(["left"]).choose(
        "子菜单",
        (MenuItem("1", "第一项"),),
    )

    assert selected == "2"
    assert returned is None
    capsys.readouterr()


def test_text_input_can_be_cancelled_with_escape_without_enter(capsys):
    menu = make_menu(["a", "b", "escape"])

    result = menu.read_text("Name: ")

    assert result is None
    capsys.readouterr()


def test_masked_text_input_supports_editing(capsys):
    menu = make_menu(["s", "e", "x", "backspace", "c", "enter"])

    result = menu.read_text("Key: ", masked=True)

    assert result == "sec"
    assert "sec" not in capsys.readouterr().out


def test_text_input_left_and_right_move_the_cursor(capsys):
    menu = make_menu(["a", "b", "left", "X", "right", "Y", "enter"])

    result = menu.read_text("Name: ")

    assert result == "aXbY"
    capsys.readouterr()


def test_ctrl_v_pastes_clipboard_text_with_unicode(capsys):
    menu = make_menu(["paste", "enter"], clipboard="https://讯飞.example/v2\n")

    result = menu.read_text("Base: ")

    assert result == "https://讯飞.example/v2"
    assert "讯飞" in capsys.readouterr().out


def test_ctrl_v_masks_clipboard_when_entering_secret(capsys):
    menu = make_menu(["paste", "enter"], clipboard="<test-api-key>")

    result = menu.read_text("Key: ", masked=True)

    assert result == "<test-api-key>"
    assert "<test-api-key>" not in capsys.readouterr().out


def test_confirm_defaults_to_reject_and_can_select_apply(capsys):
    rejected = make_menu(["enter"]).confirm("确认？")
    accepted = make_menu(["right", "enter"]).confirm("确认？")

    assert rejected is False
    assert accepted is True
    capsys.readouterr()
