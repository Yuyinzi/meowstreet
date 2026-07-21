def init_db(con):
    columns = {
        row["name"]
        for row in con.execute("pragma table_info(ism_industry_rankings)").fetchall()
    }
    if columns and "survey_type" not in columns:
        con.executescript(
            """
            alter table ism_industry_rankings rename to ism_industry_rankings_legacy;
            create table ism_industry_rankings (
                survey_type text not null,
                date text not null,
                industry text not null,
                direction text not null,
                rank integer not null,
                source text not null,
                primary key(survey_type, date, industry)
            );
            insert into ism_industry_rankings
            select 'manufacturing', date, industry, direction, rank, source
            from ism_industry_rankings_legacy;
            drop table ism_industry_rankings_legacy;
            """
        )
    con.executescript(
        """
        create table if not exists ism_industry_rankings (
            survey_type text not null,
            date text not null,
            industry text not null,
            direction text not null,
            rank integer not null,
            source text not null,
            primary key(survey_type, date, industry)
        );
        create index if not exists idx_ism_rankings_survey_date
        on ism_industry_rankings(survey_type, date);
        create table if not exists ism_industry_comments (
            survey_type text not null,
            report_month text not null,
            industry text not null,
            comment_index integer not null,
            comment_text text not null,
            source text not null,
            primary key(survey_type, report_month, industry, comment_index)
        );
        """
    )
    report_columns = {
        row["name"]
        for row in con.execute("pragma table_info(ism_report_snapshots)").fetchall()
    }
    if report_columns and "survey_type" not in report_columns:
        con.execute(
            "alter table ism_report_snapshots add column survey_type text not null default 'manufacturing'"
        )
    con.commit()


def replace_industry_rankings(con, survey_type, rows):
    con.execute(
        "delete from ism_industry_rankings where survey_type = ?", (survey_type,)
    )
    con.executemany(
        "insert into ism_industry_rankings values (?, ?, ?, ?, ?, ?)",
        [
            (
                survey_type,
                row["date"],
                row["industry"],
                row["direction"],
                row["rank"],
                row["source"],
            )
            for row in rows
        ],
    )
    con.commit()
    return len(rows)


def insert_industry_rankings(con, survey_type, rows, commit=True):
    for row in rows:
        con.execute(
            "insert or ignore into ism_industry_rankings(survey_type, date, industry, direction, rank, source) values (?, ?, ?, ?, ?, ?)",
            (
                survey_type,
                row["date"],
                row["industry"],
                row["direction"],
                row["rank"],
                row["source"],
            ),
        )
    if commit:
        con.commit()
    return len(rows)


def merge_industry_rankings(con, survey_type, rows, commit=True):
    for row in rows:
        con.execute(
            """
            insert into ism_industry_rankings(survey_type, date, industry, direction, rank, source)
            values (?, ?, ?, ?, ?, ?)
            on conflict(survey_type, date, industry) do update set
                direction = excluded.direction,
                rank = excluded.rank,
                source = excluded.source
            """,
            (
                survey_type,
                row["date"],
                row["industry"],
                row["direction"],
                row["rank"],
                row["source"],
            ),
        )
    if commit:
        con.commit()
    return len(rows)


def load_industry_rankings(con, survey_type, limit_months=None, max_date=None):
    if limit_months is not None:
        if max_date is not None:
            latest = con.execute(
                "select distinct date from ism_industry_rankings where survey_type = ? and date <= ? order by date desc limit ?",
                (survey_type, max_date, limit_months),
            ).fetchall()
        else:
            latest = con.execute(
                "select distinct date from ism_industry_rankings where survey_type = ? order by date desc limit ?",
                (survey_type, limit_months),
            ).fetchall()
        if not latest:
            return []
        dates = {row["date"] for row in latest}
        placeholders = ",".join("?" for _ in dates)
        if max_date is not None:
            rows = con.execute(
                f"""
                select survey_type, date, industry, direction, rank, source
                from ism_industry_rankings
                where survey_type = ? and date in ({placeholders}) and date <= ?
                order by date desc, direction desc, rank desc, industry
                """,
                (survey_type, *dates, max_date),
            ).fetchall()
        else:
            rows = con.execute(
                f"""
                select survey_type, date, industry, direction, rank, source
                from ism_industry_rankings
                where survey_type = ? and date in ({placeholders})
                order by date desc, direction desc, rank desc, industry
                """,
                (survey_type, *dates),
            ).fetchall()
    else:
        if max_date is not None:
            rows = con.execute(
                """
                select survey_type, date, industry, direction, rank, source
                from ism_industry_rankings
                where survey_type = ? and date <= ?
                order by date desc, direction desc, rank desc, industry
                """,
                (survey_type, max_date),
            ).fetchall()
        else:
            rows = con.execute(
                """
                select survey_type, date, industry, direction, rank, source
                from ism_industry_rankings
                where survey_type = ?
                order by date desc, direction desc, rank desc, industry
                """,
                (survey_type,),
            ).fetchall()
    return [dict(row) for row in rows]


def replace_industry_comments(con, survey_type, rows):
    con.execute(
        "delete from ism_industry_comments where survey_type = ?", (survey_type,)
    )
    con.executemany(
        "insert into ism_industry_comments(survey_type, report_month, industry, comment_index, comment_text, source) values (?, ?, ?, ?, ?, ?)",
        [
            (
                survey_type,
                row["report_month"],
                row["industry"],
                row["comment_index"],
                row["comment_text"],
                row["source"],
            )
            for row in rows
        ],
    )
    con.commit()
    return len(rows)


def insert_industry_comments(con, survey_type, rows, commit=True):
    for row in rows:
        con.execute(
            "insert or ignore into ism_industry_comments(survey_type, report_month, industry, comment_index, comment_text, source) values (?, ?, ?, ?, ?, ?)",
            (
                survey_type,
                row["report_month"],
                row["industry"],
                row["comment_index"],
                row["comment_text"],
                row["source"],
            ),
        )
    if commit:
        con.commit()
    return len(rows)


def merge_industry_comments(con, survey_type, rows, commit=True):
    for row in rows:
        con.execute(
            """
            insert into ism_industry_comments(survey_type, report_month, industry, comment_index, comment_text, source)
            values (?, ?, ?, ?, ?, ?)
            on conflict(survey_type, report_month, industry, comment_index) do update set
                comment_text = excluded.comment_text,
                source = excluded.source
            """,
            (
                survey_type,
                row["report_month"],
                row["industry"],
                row["comment_index"],
                row["comment_text"],
                row["source"],
            ),
        )
    if commit:
        con.commit()
    return len(rows)


def load_industry_comments(con, survey_type, report_month=None):
    if report_month is not None:
        rows = con.execute(
            """
            select survey_type, report_month, industry, comment_index, comment_text, source
            from ism_industry_comments
            where survey_type = ? and report_month = ?
            order by industry, comment_index
            """,
            (survey_type, report_month),
        ).fetchall()
    else:
        rows = con.execute(
            """
            select survey_type, report_month, industry, comment_index, comment_text, source
            from ism_industry_comments
            where survey_type = ?
            order by report_month desc, industry, comment_index
            """,
            (survey_type,),
        ).fetchall()
    return [dict(row) for row in rows]


def replace_report_snapshot(con, survey_type, report, comments, commit=True):
    con.execute(
        """
        insert into ism_report_snapshots(
            report_id, report_month, title, source_url, source_hash, fetched_at,
            parse_status, next_report_period, next_release_at, next_release_label,
            survey_type
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(report_id) do update set
            report_month = excluded.report_month,
            title = excluded.title,
            source_url = excluded.source_url,
            source_hash = excluded.source_hash,
            fetched_at = excluded.fetched_at,
            parse_status = excluded.parse_status,
            next_report_period = excluded.next_report_period,
            next_release_at = excluded.next_release_at,
            next_release_label = excluded.next_release_label,
            survey_type = excluded.survey_type
        """,
        (
            report["report_id"],
            report["report_month"],
            report["title"],
            report["source_url"],
            report["source_hash"],
            report["fetched_at"],
            report.get("parse_status", ""),
            report.get("next_report_period"),
            report.get("next_release_at"),
            report.get("next_release_label", ""),
            survey_type,
        ),
    )
    con.execute(
        "delete from ism_report_comments where report_id = ?",
        (report["report_id"],),
    )
    for comment in comments:
        con.execute(
            """
            insert into ism_report_comments(
                report_id, comment_index, report_month, industry, comment_text,
                source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment["report_id"],
                comment["comment_index"],
                comment["report_month"],
                comment["industry"],
                comment["comment_text"],
                comment["source_url"],
                comment["source_hash"],
            ),
        )
    if commit:
        con.commit()
    return {"reports": 1, "comments": len(comments)}


def load_latest_report_snapshot(con, survey_type):
    rows = con.execute(
        """
        select report_id, report_month, title, source_url, source_hash, fetched_at,
               parse_status, next_report_period, next_release_at, next_release_label,
               survey_type
        from ism_report_snapshots
        where survey_type = ?
        order by report_month desc
        limit 1
        """,
        (survey_type,),
    ).fetchall()
    return dict(rows[0]) if rows else None


def load_recent_report_snapshots(con, survey_type, limit=6):
    rows = con.execute(
        """
        select report_id, report_month, title, source_url, source_hash, fetched_at,
               parse_status, next_report_period, next_release_at, next_release_label,
               survey_type
        from ism_report_snapshots
        where survey_type = ?
        order by report_month desc
        limit ?
        """,
        (survey_type, limit),
    ).fetchall()
    result = [dict(row) for row in rows]
    result.reverse()
    return result


def load_existing_report_months(con, survey_type):
    rows = con.execute(
        "select report_month from ism_report_snapshots where survey_type = ?",
        (survey_type,),
    ).fetchall()
    return {row["report_month"] for row in rows}
