from range_program.check_all_report import (
    CheckTableRow,
    aggregate_counts,
    format_check_all_table,
    format_check_all_csv,
    format_summary,
    select_rows,
    select_worst_rows,
    status_sort_key,
)


def test_status_sort_order_priority() -> None:
    assert status_sort_key("OUT_OF_RANGE") < status_sort_key("REPOSITION")
    assert status_sort_key("REPOSITION") < status_sort_key("STALE")
    assert status_sort_key("STALE") < status_sort_key("WARNING")
    assert status_sort_key("WARNING") < status_sort_key("OK")
    assert status_sort_key("ERROR") > status_sort_key("OUT_OF_RANGE")


def test_table_rows_sort_by_status_then_symbol() -> None:
    rows = [
        CheckTableRow("ETH", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK"),
        CheckTableRow("BTC", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 5.0, "OUT_OF_RANGE"),
        CheckTableRow("SOL", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 2.0, "WARNING"),
    ]
    rows.sort(key=lambda r: (r.sort_rank, r.symbol))
    assert [r.symbol for r in rows] == ["BTC", "SOL", "ETH"]


def test_aggregate_counts() -> None:
    rows = [
        CheckTableRow("A", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK"),
        CheckTableRow("B", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK"),
        CheckTableRow("C", "—", None, "—", None, None, "—", None, None, "—", None, "—", None, "x", None, "ERROR"),
    ]
    c = aggregate_counts(rows)
    assert c["OK"] == 2
    assert c["ERROR"] == 1


def test_select_rows_filter_and_top_n() -> None:
    rows = [
        CheckTableRow("ETH", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK"),
        CheckTableRow("BTC", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 10.0, "OUT_OF_RANGE"),
        CheckTableRow("SOL", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 3.0, "WARNING"),
        CheckTableRow("AAA", "—", None, "—", None, None, "—", None, None, "—", None, "—", None, "x", None, "ERROR"),
    ]

    problems = select_rows(rows, exclude_ok_by_default=True)
    assert {r.status for r in problems} == {"OUT_OF_RANGE", "WARNING", "ERROR"}

    only_critical = select_rows(rows, statuses={"OUT_OF_RANGE", "ERROR"})
    assert [r.status for r in only_critical] == ["OUT_OF_RANGE", "ERROR"]

    top1 = select_rows(rows, exclude_ok_by_default=True, top_n=1)
    assert len(top1) == 1
    assert top1[0].status == "OUT_OF_RANGE"


def test_format_table_and_summary_smoke() -> None:
    rows = [
        CheckTableRow("BTC", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 10.0, "OUT_OF_RANGE"),
        CheckTableRow("ETH", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK"),
    ]
    txt = format_check_all_table(rows)
    assert "SYMBOL" in txt and "BTC" in txt
    summ = format_summary(aggregate_counts(rows))
    assert "Summary" in summ and "OK" in summ


def test_format_csv_and_tsv_smoke() -> None:
    rows = [
        CheckTableRow("BTC", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 10.0, "OUT_OF_RANGE", "do it"),
        CheckTableRow("ETH", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 1.0, "OK", "ok"),
    ]
    csv_txt = format_check_all_csv(rows, delimiter=",")
    assert "symbol,status,price" in csv_txt
    tsv_txt = format_check_all_csv(rows, delimiter="\t")
    assert "symbol\tstatus\tprice" in tsv_txt


def test_select_worst_rows_prefers_higher_deviation_within_status() -> None:
    rows = [
        CheckTableRow("AAA", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 2.0, "WARNING"),
        CheckTableRow("BBB", "1", 1.0, "a", 1.0, 2.0, "r", 1.0, 2.0, "1%", 1.0, "1%", 1.0, "1%", 8.0, "WARNING"),
    ]
    worst = select_worst_rows(rows, top_n=1)
    assert worst[0].symbol == "BBB"
