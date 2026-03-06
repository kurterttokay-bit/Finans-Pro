import pandas as pd
import streamlit as st

SHEET_COLUMNS = [
    "kayit_tarihi",
    "belge_tarihi",
    "firma_adi",
    "evrak_tipi",
    "evrak_no",
    "vergi_kimlik_no",
    "para_birimi",
    "ara_toplam",
    "kdv_orani",
    "kdv_tutari",
    "genel_toplam",
    "kategori",
    "odeme_durumu",
    "aciklama",
    "ham_metin",
    "kaynak_dosya",
    "created_at",
    "updated_at",
]


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gerekli kolonları garanti eder, eksik olanları ekler.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    df = df.copy()

    for col in SHEET_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Sıralamayı sabitle
    df = df[SHEET_COLUMNS]
    return df


def _drop_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tamamen boş satırları temizler.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    df = df.copy()

    # Boş stringleri NaN gibi ele al
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    df = df.dropna(how="all")

    # Tekrar boş stringe çevir
    df = df.fillna("")
    return df


def read_sheet(conn, worksheet=None) -> pd.DataFrame:
    """
    Google Sheets'ten veriyi okur, temizler ve standart kolonlarla döner.
    """
    try:
        if worksheet:
            df = conn.read(worksheet=worksheet)
        else:
            df = conn.read()
    except Exception:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    if df is None:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    df = _ensure_columns(df)
    df = _drop_empty_rows(df)
    return df


def append_row(conn, record: dict, worksheet=None) -> pd.DataFrame:
    """
    Tek bir kaydı sheet'e güvenli şekilde ekler.
    Önce mevcut veriyi okur, sonra alta ekleyip tamamını update eder.
    """
    df = read_sheet(conn, worksheet=worksheet)

    # Record'u sadece beklenen kolonlarla sınırla
    clean_record = {col: record.get(col, "") for col in SHEET_COLUMNS}
    new_row = pd.DataFrame([clean_record])

    updated_df = pd.concat([df, new_row], ignore_index=True)
    updated_df = _ensure_columns(updated_df)
    updated_df = _drop_empty_rows(updated_df)

    if worksheet:
        conn.update(worksheet=worksheet, data=updated_df)
    else:
        conn.update(data=updated_df)

    return updated_df


def replace_sheet(conn, df: pd.DataFrame, worksheet=None) -> pd.DataFrame:
    """
    Tüm sheet'i kontrollü şekilde yeniden yazar.
    """
    df = _ensure_columns(df)
    df = _drop_empty_rows(df)

    if worksheet:
        conn.update(worksheet=worksheet, data=df)
    else:
        conn.update(data=df)

    return df


def clear_empty_cache_view(conn, worksheet=None) -> pd.DataFrame:
    """
    Sheet'i tekrar okuyup boş satırları temizleyerek geri yazar.
    Satır silme/elle düzenleme sonrası toparlamak için kullanılabilir.
    """
    df = read_sheet(conn, worksheet=worksheet)
    return replace_sheet(conn, df, worksheet=worksheet)
