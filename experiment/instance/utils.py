def format_bytes(bytes_value: float) -> str:
    """
    バイトを人間が読みやすい形式に変換します。

    引数:
        bytes_value (float): バイト単位のサイズ

    戻り値:
        str: 適切な単位（B、KB、MB、GB、TB、PB）を持つフォーマット済み文字列
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.2f} PB"
