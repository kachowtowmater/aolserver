"""FDO builders for host screens, in AOL 3.0's own form vocabulary."""
from .util import compile_fdo, fdo_text

TEXT_CHUNK = 200


def _appends(text: str) -> str:
    # the client swallows the byte after a CR, so lines end CR LF like DOS text
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return "\n".join(f'      man_append_data <"{fdo_text(text[i:i + TEXT_CHUNK])}">'
                     for i in range(0, len(text), TEXT_CHUNK))


def window_gid(key: str) -> str:
    """Stable global id per window kind ('signup', 'quote', ...) so a re-send replaces it.
    Derived from the name (not a counter) so hot reloads never reshuffle ids."""
    import zlib
    return f"32-{50000 + zlib.crc32(key.encode()) % 15000}"  # form-style id, above any real AOL form


def _wrap(body: str, response_id: bytes | None, window: str | None = None) -> bytes:
    rid = f"  man_set_response_id <{int.from_bytes(response_id, 'big')}>\n" if response_id else ""
    pre, close = "", b""
    if window:
        # closing the old copy must be its own stream: a close takes effect only after the
        # stream ends, so presetting the same id in that stream would nest inside the old one
        close = close_window(window)
        pre = f"  man_preset_gid <{window_gid(window)}>\n"
    return close + compile_fdo(
        f"uni_start_stream <00x>\n{rid}{pre}{body}\n  man_update_display\n  uni_wait_off\nuni_end_stream <00x>")


def list_window(title: str, intro: str, items: list[tuple[str, int]], buttons=(), art: str | None = None,
                response_id=None, width: int = 52, window: str | None = None) -> bytes:
    """Window: optional banner art, intro text, a list whose entries send `zA <n>`,
    then buttons [(label, fdo_action_atoms)]."""
    lines = ['  man_start_object <ind_group, "%s">' % fdo_text(title),
             "    mat_orientation <vcf>", "    mat_position <center_center>"]
    first = True

    def child(kind, label=""):
        nonlocal first
        verb = "man_start_object" if first else "man_start_sibling"
        first = False
        lines.append(f'    {verb} <{kind}, "{fdo_text(label)}">')

    if art:
        child("ornament")
        lines.append(f"      mat_art_id <{art}>")
    if intro:
        child("view")
        lines += [f"      mat_size <{width}, 3>", _appends(intro), "      man_end_data"]
    child("dss_list")
    lines += [f"      mat_size <{width}, 12>", "      mat_relative_tag <1>", "      mat_bool_default_send <no>"]
    for i, (label, n) in enumerate(items):
        verb = "man_start_object" if i == 0 else "man_start_sibling"
        lines += [f'      {verb} <trigger, "{fdo_text(label[:90])}">',
                  "        act_replace_select_action",
                  f'          <\n          uni_start_stream_wait_on <00x>\n          sm_send_token_arg <"zA", {n}>\n          >']
    if items:
        lines.append("      man_end_object")
    if buttons:
        child("org_group")
        lines.append("      mat_orientation <hcf>")
        for i, (label, action) in enumerate(buttons):
            verb = "man_start_object" if i == 0 else "man_start_sibling"
            lines += [f'      {verb} <trigger, "{fdo_text(label)}">', "        act_replace_select_action",
                      f"          <\n          uni_start_stream_wait_on <00x>\n{action}\n          >"]
        lines.append("      man_end_object")
    lines.append("    man_end_object")
    return _wrap("\n".join(lines), response_id, window)


def text_window(title: str, text: str, response_id=None, window: str | None = None, width: int = 60, height: int = 16) -> bytes:
    body = "\n".join(['  man_start_object <ind_group, "%s">' % fdo_text(title),
                      "    mat_orientation <vff>", "    mat_position <center_center>",
                      '    man_start_object <view, "">', f"      mat_size <{width}, {height}>",
                      _appends(text), "      man_end_data", "    man_end_object"])
    return _wrap(body, response_id, window)


def input_window(title: str, prompt: str, button: str, token: str, intro: str = "", response_id=None, window: str | None = None) -> bytes:
    """One edit box + button that sends `token` with the typed text (like the Keyword window)."""
    body = "\n".join([
        '  man_start_object <ind_group, "%s">' % fdo_text(title),
        "    mat_orientation <vcf>", "    mat_position <center_center>",
        *(['    man_start_object <view, "">', "      mat_size <44, 3>", _appends(intro), "      man_end_data",
           f'    man_start_sibling <edit_view, "{fdo_text(prompt)}">'] if intro else
          [f'    man_start_object <edit_view, "{fdo_text(prompt)}">']),
        "      mat_size <30, 1, 40>", "      mat_relative_tag <1>", "      mat_title_pos <left | center>",
        "      mat_bool_writeable <yes>",
        f'    man_start_sibling <trigger, "{fdo_text(button)}">',
        "      mat_bool_default <yes>",
        "      act_replace_select_action",
        "          <\n          uni_start_stream\n            de_start_extraction\n"
        f'            buf_set_token <"{token}">\n            man_set_context_relative <1>\n'
        "            de_get_data\n            man_end_context\n            de_end_extraction\n"
        "            buf_close_buffer\n          uni_end_stream\n          >",
        "    man_end_object"])
    return _wrap(body, response_id, window)


def page_window(title: str, text: str, links: list[tuple[str, int]], response_id=None, window: str | None = None,
                links_title: str = "Links on this page:") -> bytes:
    """Text pane on top, clickable links list (zA) underneath: the 2026 web, 1997 window."""
    lines = ['  man_start_object <ind_group, "%s">' % fdo_text(title[:60]),
             "    mat_orientation <vcf>", "    mat_position <center_center>",
             '    man_start_object <view, "">', "      mat_size <64, 13>", _appends(text), "      man_end_data"]
    if links:
        lines += [f'    man_start_sibling <dss_list, "{fdo_text(links_title)}">', "      mat_size <64, 6>",
                  "      mat_title_pos <left | top_or_left>", "      mat_bool_default_send <no>"]
        for i, (label, n) in enumerate(links):
            verb = "man_start_object" if i == 0 else "man_start_sibling"
            lines += [f'      {verb} <trigger, "{fdo_text(label[:80])}">', "        act_replace_select_action",
                      f'          <\n          uni_start_stream_wait_on <00x>\n          sm_send_token_arg <"zA", {n}>\n          >']
        lines.append("      man_end_object")
    lines.append("    man_end_object")
    return _wrap("\n".join(lines), response_id, window)


def form_window(title: str, intro: str, fields: list[tuple[str, int, str]], button: str, token: str,
                response_id=None, window: str | None = None) -> bytes:
    """Several labelled edit boxes [(label, width, preset)] + one button sending `token` with every
    field as de_data, in order (how AOL's own registration/profile forms did it)."""
    lines = ['  man_start_object <ind_group, "%s">' % fdo_text(title), "    mat_orientation <vcf>",
             "    mat_position <center_center>", '    man_start_object <view, "">', "      mat_size <46, 3>",
             _appends(intro), "      man_end_data"]
    for i, (label, width, preset) in enumerate(fields, start=1):
        lines += [f'    man_start_sibling <edit_view, "{fdo_text(label)}">', f"      mat_size <{width}, 1, 120>",
                  f"      mat_relative_tag <{i}>", "      mat_title_pos <left | center>", "      mat_bool_writeable <yes>"]
        if "password" in label.lower():
            lines.append("      mat_bool_hidden <yes>")
        if preset:
            lines.append(f'      man_append_data <"{fdo_text(preset)}">')
    gets = "\n".join(f"            man_set_context_relative <{i}>\n            de_get_data\n            man_end_context"
                      for i in range(1, len(fields) + 1))
    lines += [f'    man_start_sibling <trigger, "{fdo_text(button)}">', "      mat_bool_default <yes>",
              "      act_replace_select_action",
              f'          <\n          uni_start_stream\n            de_start_extraction\n            buf_set_token <"{token}">\n'
              f"{gets}\n            de_end_extraction\n            buf_close_buffer\n          uni_end_stream\n          >",
              "    man_end_object"]
    return _wrap("\n".join(lines), response_id, window)


def close_window(window: str) -> bytes:
    """Close a host window: set context to its global id, man_close (man_close <gid> doesn't
    close host-built windows; this is safe when the window doesn't exist)."""
    return compile_fdo(f"uni_start_stream <00x>\n  man_set_context_globalid <{window_gid(window)}>\n  man_close\n"
                       "  man_update_display\nuni_end_stream <00x>")
