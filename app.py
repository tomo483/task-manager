import streamlit as st
import json
import os
import uuid
import re
from datetime import date
from supabase import create_client

# =========================
# 基本設定
# =========================

st.set_page_config(
    page_title="課題管理アプリ",
    page_icon="📚",
    layout="wide"
)

# =========================
# Supabase接続
# =========================

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


# ログイン状態を復元
if st.session_state.get("logged_in") and st.session_state.get("auth_tokens"):
    try:
        supabase.auth.set_session(
            st.session_state.auth_tokens["access_token"],
            st.session_state.auth_tokens["refresh_token"]
        )
    except Exception:
        st.session_state.logged_in = False
        st.session_state.pop("auth_tokens", None)
        st.session_state.pop("user_id", None)


# =========================
# ログイン・新規登録
# =========================

def username_to_email(username):
    # ユーザーIDを内部用のメール形式に変換
    return username.lower() + "@login.taskmanager.local"


def login_screen():

    st.title("📚 課題管理アプリ")

    login_tab, signup_tab = st.tabs([
        "ログイン",
        "新規登録"
    ])

    with login_tab:

        st.subheader("ログイン")

        username = st.text_input(
            "ユーザーID",
            key="login_username"
        )

        password = st.text_input(
            "パスワード",
            type="password",
            key="login_password"
        )

        if st.button("ログイン", use_container_width=True):

            if not username or not password:
                st.warning("ユーザーIDとパスワードを入力してください。")

            else:
                try:
                    email = username_to_email(username)

                    result = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })

                    st.session_state.auth_tokens = {
                        "access_token": result.session.access_token,
                        "refresh_token": result.session.refresh_token
                    }

                    st.session_state.user_id = result.user.id
                    st.session_state.logged_in = True

                    st.rerun()

                except Exception:
                    st.error("ユーザーIDまたはパスワードが違います。")

    with signup_tab:

        st.subheader("新規登録")

        new_username = st.text_input(
            "ユーザーID（3〜20文字・英数字と_）",
            key="signup_username"
        )

        new_password = st.text_input(
            "パスワード（8文字以上）",
            type="password",
            key="signup_password"
        )

        confirm_password = st.text_input(
            "パスワード（確認用）",
            type="password",
            key="confirm_password"
        )

        if st.button("アカウントを作成", use_container_width=True):

            if not re.fullmatch(r"[a-zA-Z0-9_]{3,20}", new_username):
                st.error("ユーザーIDは半角英数字と_で3〜20文字にしてください。")

            elif len(new_password) < 8:
                st.error("パスワードは8文字以上にしてください。")

            elif new_password != confirm_password:
                st.error("パスワードが一致しません。")

            else:
                try:
                    email = username_to_email(new_username)

                    result = supabase.auth.sign_up({
                        "email": email,
                        "password": new_password
                    })

                    if result.session is None:
                        st.error("登録できませんでした。Supabaseのメール確認設定を確認してください。")

                    else:
                        st.session_state.auth_tokens = {
                            "access_token": result.session.access_token,
                            "refresh_token": result.session.refresh_token
                        }

                        st.session_state.user_id = result.user.id
                        st.session_state.logged_in = True

                        st.success("アカウントを作成しました！")
                        st.rerun()

                except Exception as e:
                    st.error(f"登録エラー：{e}")

                    # =========================
# ログイン状態の確認
# =========================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_screen()
    st.stop()


# =========================
# ログアウト
# =========================

if st.sidebar.button("ログアウト", use_container_width=True):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    st.session_state.logged_in = False
    st.session_state.pop("auth_tokens", None)
    st.session_state.pop("user_id", None)
    st.session_state.pop("tasks", None)

    st.rerun()


DATA_FILE = "tasks.json"

st.title("📚 課題管理アプリ")


# =========================
# データ読み込み・保存
# =========================

def calculate_progress(task):
    estimated = float(task["estimated"])
    actual = float(task["actual"])

    if estimated <= 0:
        return 0

    return min(100, max(0, actual / estimated * 100))


def load_tasks():
    try:
        result = (
            supabase.table("tasks")
            .select("data")
            .eq("user_id", st.session_state.user_id)
            .execute()
        )

        tasks = [row["data"] for row in result.data]

        for task in tasks:
            task.setdefault("id", str(uuid.uuid4()))
            task.setdefault("name", "名称未設定")
            task.setdefault("deadline", date.today().isoformat())
            task.setdefault("estimated", 1.0)
            task.setdefault("actual", 0.0)
            task.setdefault("completed", False)
            task.setdefault("logs", [])
            task.setdefault("completion_prompt_dismissed", False)

            base = calculate_progress(task)

            if "progress_adjustment" not in task:
                old_progress = float(task.get("progress", base))
                task["progress_adjustment"] = old_progress - base

        return tasks

    except Exception as e:
        st.error(f"課題データの読み込みに失敗しました：{e}")
        return []



def save_tasks():
    try:
        user_id = st.session_state.user_id

        # このユーザーの既存データを削除
        supabase.table("tasks").delete().eq(
            "user_id", user_id
        ).execute()

        # 現在の課題を保存
        if st.session_state.tasks:
            records = [
                {
                    "id": task["id"],
                    "user_id": user_id,
                    "data": task
                }
                for task in st.session_state.tasks
            ]

            supabase.table("tasks").insert(records).execute()

    except Exception as e:
        st.error(f"課題データの保存に失敗しました：{e}")



if "tasks" not in st.session_state:
    st.session_state.tasks = load_tasks()


# =========================
# 進捗率・共通処理
# =========================

def calculate_progress(task):
    estimated = float(task["estimated"])
    actual = float(task["actual"])

    if estimated <= 0:
        return 0

    return min(100, max(0, actual / estimated * 100))


def get_progress(task):
    base = calculate_progress(task)
    adjustment = float(task.get("progress_adjustment", 0))

    return round(min(100, max(0, base + adjustment)))


def get_remaining(task):
    return max(
        0,
        float(task["estimated"]) - float(task["actual"])
    )


def get_days_left(task):
    try:
        deadline = date.fromisoformat(task["deadline"])
        return (deadline - date.today()).days
    except ValueError:
        return 9999


def get_priority(task):
    days = get_days_left(task)

    if days < 0:
        return 0
    elif days <= 2:
        return 1
    elif days <= 7:
        return 2
    else:
        return 3


def get_priority_name(task):
    names = {
        0: "期限切れ",
        1: "最優先",
        2: "高",
        3: "通常"
    }

    return names[get_priority(task)]


def find_task(task_id):
    for task in st.session_state.tasks:
        if task["id"] == task_id:
            return task

    return None


# スライダーを変更したときの処理
def update_progress(task_id):
    task = find_task(task_id)

    if task:
        selected_progress = st.session_state[
            f"progress_{task_id}"
        ]

        base = calculate_progress(task)

        # 自動計算との差分を保存
        task["progress_adjustment"] = selected_progress - base

        task["completion_prompt_dismissed"] = False

        save_tasks()


# =========================
# ページ構成
# =========================

dashboard_tab, detail_tab, completed_tab, history_tab = st.tabs([
    "📊 ダッシュボード",
    "📝 課題の詳細",
    "✅ 完了済み",
    "⏱️ 作業履歴"
])


# =========================
# ① ダッシュボード
# =========================

with dashboard_tab:

    st.header("課題一覧")

    # 未完了課題だけを表示
    active_tasks = [
        task for task in st.session_state.tasks
        if not task["completed"]
    ]

    completed_tasks = [
        task for task in st.session_state.tasks
        if task["completed"]
    ]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("未完了の課題", len(active_tasks))

    with col2:
        st.metric("完了した課題", len(completed_tasks))

    with col3:
        total_remaining = sum(
            get_remaining(task) for task in active_tasks
        )
        st.metric("残り作業時間", f"{total_remaining:.1f}時間")

    st.divider()

    # 課題追加
    with st.expander("➕ 新しい課題を追加"):

        with st.form("add_task_form"):

            new_name = st.text_input("課題名")

            new_deadline = st.date_input(
                "締め切り",
                value=date.today()
            )

            new_estimated = st.number_input(
                "予想作業時間（時間）",
                min_value=0.1,
                value=3.0,
                step=0.5
            )

            add_button = st.form_submit_button("課題を追加")

            if add_button:
                if new_name.strip():

                    new_task = {
                        "id": str(uuid.uuid4()),
                        "name": new_name,
                        "deadline": new_deadline.isoformat(),
                        "estimated": new_estimated,
                        "actual": 0.0,
                        "progress_adjustment": 0,
                        "completed": False,
                        "logs": [],
                        "completion_prompt_dismissed": False
                    }

                    st.session_state.tasks.append(new_task)
                    save_tasks()

                    st.success("課題を追加しました。")
                    st.rerun()

                else:
                    st.warning("課題名を入力してください。")

    # 並び替え
    st.subheader("課題の並び替え")

    sort_option = st.selectbox(
        "表示順",
        [
            "優先度順",
            "締め切りが近い順",
            "残り作業時間が多い順",
            "残り作業時間が少ない順",
            "進捗率が低い順",
            "進捗率が高い順",
            "課題名順"
        ]
    )

    if sort_option == "優先度順":
        active_tasks.sort(
            key=lambda t: (
                get_priority(t),
                get_days_left(t),
                -get_remaining(t)
            )
        )

    elif sort_option == "締め切りが近い順":
        active_tasks.sort(
            key=lambda t: get_days_left(t)
        )

    elif sort_option == "残り作業時間が多い順":
        active_tasks.sort(
            key=lambda t: get_remaining(t),
            reverse=True
        )

    elif sort_option == "残り作業時間が少ない順":
        active_tasks.sort(
            key=lambda t: get_remaining(t)
        )

    elif sort_option == "進捗率が低い順":
        active_tasks.sort(
            key=lambda t: get_progress(t)
        )

    elif sort_option == "進捗率が高い順":
        active_tasks.sort(
            key=lambda t: get_progress(t),
            reverse=True
        )

    elif sort_option == "課題名順":
        active_tasks.sort(
            key=lambda t: t["name"]
        )

    st.divider()

    # 課題一覧
    if not active_tasks:
        st.info("現在、未完了の課題はありません。")

    for task in active_tasks:

        task_id = task["id"]

        with st.container(border=True):

            col1, col2 = st.columns([4, 1])

            with col1:
                st.subheader(task["name"])

            with col2:
                st.write(f"**{get_priority_name(task)}**")

            # 締め切り
            days = get_days_left(task)

            if days < 0:
                st.error(f"締め切りを{abs(days)}日過ぎています")
            elif days == 0:
                st.warning("締め切りは今日です")
            else:
                st.caption(f"締め切りまであと {days} 日")

            # 作業時間
            col1, col2 = st.columns(2)

            with col1:
                st.write(
                    f"実施時間：{task['actual']:.1f}時間"
                )

            with col2:
                st.write(
                    f"予想時間：{task['estimated']:.1f}時間"
                )

            # 自動計算と調整後の進捗率
            base_progress = calculate_progress(task)
            progress = get_progress(task)

            st.write(
                f"進捗率：{progress}% "
                f"（時間からの自動計算：{base_progress:.0f}%）"
            )

            st.progress(progress / 100)

            # スライダー
            slider_key = f"progress_{task_id}"

            if slider_key not in st.session_state:
                st.session_state[slider_key] = progress

            st.slider(
                "進捗率を微調整",
                min_value=0,
                max_value=100,
                step=1,
                key=slider_key,
                on_change=update_progress,
                args=(task_id,)
            )

            # 完了確認
            should_ask_completion = (
                (
                    get_progress(task) >= 100
                    or float(task["actual"]) >= float(task["estimated"])
                )
                and not task["completion_prompt_dismissed"]
            )

            if should_ask_completion:

                st.warning("この課題を完了にしますか？")

                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "完了にする",
                        key=f"complete_{task_id}"
                    ):
                        task["completed"] = True
                        task["progress_adjustment"] = 100 - calculate_progress(task)
                        save_tasks()
                        st.rerun()

                with col2:
                    if st.button(
                        "まだ完了ではない",
                        key=f"not_complete_{task_id}"
                    ):
                        task["completion_prompt_dismissed"] = True
                        save_tasks()
                        st.rerun()

            # 課題編集
            with st.expander("✏️ 課題を編集"):

                with st.form(f"edit_{task_id}"):

                    edit_name = st.text_input(
                        "課題名",
                        value=task["name"]
                    )

                    edit_deadline = st.date_input(
                        "締め切り",
                        value=date.fromisoformat(task["deadline"]),
                        key=f"deadline_{task_id}"
                    )

                    edit_estimated = st.number_input(
                        "予想作業時間",
                        min_value=0.1,
                        value=float(task["estimated"]),
                        step=0.5,
                        key=f"estimated_{task_id}"
                    )

                    edit_actual = st.number_input(
                        "実施時間",
                        min_value=0.0,
                        value=float(task["actual"]),
                        step=0.5,
                        key=f"actual_{task_id}"
                    )

                    save_button = st.form_submit_button("変更を保存")

                    if save_button:

                        if edit_name.strip():

                            task["name"] = edit_name
                            task["deadline"] = edit_deadline.isoformat()
                            task["estimated"] = edit_estimated
                            task["actual"] = edit_actual
                            task["completion_prompt_dismissed"] = False

                            # 時間変更後も手動調整分は維持
                            
                            save_tasks()
                            st.success("変更を保存しました。")
                            st.rerun()

                        else:
                            st.warning("課題名を入力してください。")

            # 作業時間記録
            with st.expander("⏱️ 作業時間を記録"):

                with st.form(f"log_{task_id}"):

                    work_hours = st.number_input(
                        "今回の作業時間（時間）",
                        min_value=0.1,
                        value=1.0,
                        step=0.5,
                        key=f"work_{task_id}"
                    )

                    work_date = st.date_input(
                        "作業した日",
                        value=date.today(),
                        key=f"work_date_{task_id}"
                    )

                    work_content = st.text_input(
                        "作業内容",
                        key=f"work_content_{task_id}"
                    )

                    log_button = st.form_submit_button("記録する")

                    if log_button:

                        task["actual"] += work_hours

                        task["logs"].append({
                            "date": work_date.isoformat(),
                            "hours": work_hours,
                            "content": work_content
                        })

                        task["completion_prompt_dismissed"] = False

                        # 自動計算後の進捗率をスライダーにも反映
                    
                        save_tasks()

                        st.success("作業時間を記録しました。")
                        st.rerun()


# =========================
# ② 課題の詳細
# =========================

with detail_tab:

    st.header("課題の詳細")

    if not st.session_state.tasks:
        st.info("まだ課題が登録されていません。")

    else:

        # IDは内部で使い、画面には課題名だけを表示
        task_ids = [
            task["id"] for task in st.session_state.tasks
        ]

        selected_id = st.selectbox(
            "確認する課題を選択",
            options=task_ids,
            format_func=lambda task_id: find_task(task_id)["name"]
        )

        selected_task = find_task(selected_id)

        if selected_task:

            st.subheader(selected_task["name"])

            if selected_task["completed"]:
                st.success("完了済み")
            else:
                st.write(
                    f"締め切り：{selected_task['deadline']}"
                )

            base_progress = calculate_progress(selected_task)
            progress = get_progress(selected_task)

            st.write(
                f"進捗率：{progress}% "
                f"（時間からの自動計算：{base_progress:.0f}%）"
            )

            st.progress(progress / 100)

            st.divider()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "予想作業時間",
                    f"{selected_task['estimated']:.1f}時間"
                )

            with col2:
                st.metric(
                    "実施時間",
                    f"{selected_task['actual']:.1f}時間"
                )

            with col3:
                st.metric(
                    "残り予想時間",
                    f"{get_remaining(selected_task):.1f}時間"
                )

            st.divider()

            st.subheader("作業履歴")

            logs = selected_task.get("logs", [])

            if logs:

                for log in sorted(
                    logs,
                    key=lambda x: x["date"],
                    reverse=True
                ):

                    st.write(
                        f"**{log['date']}**　"
                        f"{log['hours']}時間"
                    )

                    if log.get("content"):
                        st.caption(log["content"])

                    st.divider()

            else:
                st.info("まだ作業履歴はありません。")


# =========================
# ③ 完了済み
# =========================

with completed_tab:

    st.header("完了済みの課題")

    completed_tasks = [
        task for task in st.session_state.tasks
        if task["completed"]
    ]

    if not completed_tasks:
        st.info("完了した課題はまだありません。")

    for task in completed_tasks:

        with st.container(border=True):

            st.subheader(task["name"])

            st.write(f"締め切り：{task['deadline']}")

            st.write(
                f"実施時間：{task['actual']:.1f}時間 / "
                f"予想時間：{task['estimated']:.1f}時間"
            )

            st.write("進捗率：100%")

            if st.button(
                "未完了に戻す",
                key=f"restore_{task['id']}"
            ):

                task["completed"] = False
                task["completion_prompt_dismissed"] = True

                save_tasks()
                st.rerun()


# =========================
# ④ 作業履歴
# =========================

with history_tab:

    st.header("すべての作業履歴")

    all_logs = []

    for task in st.session_state.tasks:

        for log in task.get("logs", []):

            all_logs.append({
                "date": log["date"],
                "name": task["name"],
                "hours": log["hours"],
                "content": log.get("content", "")
            })

    all_logs.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    if not all_logs:
        st.info("作業履歴はまだありません。")

    else:

        total_hours = sum(
            log["hours"] for log in all_logs
        )

        st.metric(
            "これまでの総作業時間",
            f"{total_hours:.1f}時間"
        )

        st.divider()

        for log in all_logs:

            with st.container(border=True):

                st.write(f"**{log['name']}**")
                st.caption(log["date"])

                st.write(
                    f"作業時間：{log['hours']}時間"
                )

                if log["content"]:
                    st.write(f"作業内容：{log['content']}")
