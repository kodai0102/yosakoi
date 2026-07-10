import csv
import io
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.access_log import AccessLog
from app.models.dept_user import DeptUser
from app.models.download_history import DownloadHistory
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.activity_logs import record_activity
from app.services.auth import APP_TIMEZONE, display_datetime, normalize_datetime
from app.services.passwords import hash_password

router = APIRouter(tags=["admin-users"])
templates = Jinja2Templates(directory="app/templates")


def parse_csv_date(value: str, end_of_day: bool = False) -> datetime:
    parsed = date.fromisoformat(value)
    parsed_time = time.max if end_of_day else time.min
    return datetime.combine(parsed, parsed_time, tzinfo=APP_TIMEZONE)


def datetime_local(value: datetime) -> str:
    return display_datetime(value).strftime("%Y-%m-%dT%H:%M")


templates.env.filters["datetime_local"] = datetime_local


def ensure_valid_period(valid_from: datetime, valid_to: datetime) -> None:
    if valid_from > valid_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="利用開始日時は利用終了日時以前にしてください",
        )


def form_error_message(exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    field = ".".join(str(item) for item in first_error.get("loc", []))
    message = first_error.get("msg", "入力内容を確認してください")
    if field == "password" and first_error.get("type") == "string_too_short":
        return "パスワードは8文字以上で入力してください"
    if field == "login_id":
        return f"ログインID: {message}"
    if field == "display_name":
        return f"表示名: {message}"
    if field == "role":
        return "権限は admin または member を選択してください"
    return message


def user_form_values(
    *,
    login_id: str | None = None,
    display_name: str | None = None,
    role: str | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    is_active: bool = True,
) -> dict[str, object]:
    return {
        "login_id": login_id or "",
        "display_name": display_name or "",
        "role": role or "member",
        "valid_from": valid_from.strftime("%Y-%m-%dT%H:%M") if valid_from else "",
        "valid_to": valid_to.strftime("%Y-%m-%dT%H:%M") if valid_to else "",
        "is_active": is_active,
    }


def render_user_form(
    request: Request,
    current_user: DeptUser,
    *,
    user: DeptUser | None,
    error: str | None,
    values: dict[str, object] | None = None,
    response_status: int = status.HTTP_400_BAD_REQUEST,
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/user_form.html",
        {
            "request": request,
            "current_user": current_user,
            "user": user,
            "error": error,
            "values": values,
        },
        status_code=response_status,
    )


async def find_user_by_login_id(db: AsyncSession, login_id: str) -> DeptUser | None:
    result = await db.execute(select(DeptUser).where(DeptUser.user_id == login_id))
    return result.scalar_one_or_none()


async def find_user_by_no(db: AsyncSession, user_no: int) -> DeptUser | None:
    result = await db.execute(select(DeptUser).where(DeptUser.user_no == user_no))
    return result.scalar_one_or_none()


@router.get("/admin/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(DeptUser).order_by(DeptUser.user_no))
    users = result.scalars().all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "current_user": current_user, "users": users},
    )


@router.get("/admin/users/new", response_class=HTMLResponse)
async def new_user_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return render_user_form(
        request,
        current_user,
        user=None,
        error=None,
        values=None,
        response_status=status.HTTP_200_OK,
    )


@router.post("/admin/users", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    login_id: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    valid_from: datetime = Form(...),
    valid_to: datetime = Form(...),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    values = user_form_values(
        login_id=login_id,
        display_name=display_name,
        role=role,
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=is_active,
    )
    try:
        payload = UserCreate(
            login_id=login_id,
            display_name=display_name,
            password=password,
            role=role,
            valid_from=valid_from,
            valid_to=valid_to,
            is_active=is_active,
        )
        await create_user(db, request, payload, current_user)
    except ValidationError as exc:
        return render_user_form(
            request,
            current_user,
            user=None,
            error=form_error_message(exc),
            values=values,
        )
    except HTTPException as exc:
        return render_user_form(
            request,
            current_user,
            user=None,
            error=str(exc.detail),
            values=values,
            response_status=exc.status_code,
        )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_page(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    user = await find_user_by_no(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが存在しません")
    return render_user_form(
        request,
        current_user,
        user=user,
        error=None,
        values=None,
        response_status=status.HTTP_200_OK,
    )


@router.post("/admin/users/{user_id}", response_class=HTMLResponse)
async def update_user_form(
    request: Request,
    user_id: int,
    display_name: str = Form(...),
    password: str = Form(""),
    role: str = Form(...),
    valid_from: datetime = Form(...),
    valid_to: datetime = Form(...),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    user = await find_user_by_no(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが存在しません")

    values = user_form_values(
        display_name=display_name,
        role=role,
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=is_active,
    )
    try:
        payload = UserUpdate(
            display_name=display_name,
            password=password or None,
            role=role,
            valid_from=valid_from,
            valid_to=valid_to,
            is_active=is_active,
        )
        await update_user(db, request, user_id, payload, current_user)
    except ValidationError as exc:
        return render_user_form(
            request,
            current_user,
            user=user,
            error=form_error_message(exc),
            values=values,
        )
    except HTTPException as exc:
        return render_user_form(
            request,
            current_user,
            user=user,
            error=str(exc.detail),
            values=values,
            response_status=exc.status_code,
        )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/delete", response_class=HTMLResponse)
async def delete_user_form(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
):
    await delete_user(db, request, user_id, current_user)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/users/import", response_class=HTMLResponse)
async def import_users_page(
    request: Request,
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "admin/user_import.html",
        {"request": request, "current_user": current_user, "result": None},
    )


@router.post("/admin/users/import", response_class=HTMLResponse)
async def import_users_form(
    request: Request,
    file: UploadFile = File(...),
    initial_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> HTMLResponse:
    result = await import_users_from_csv(db, request, file, initial_password, current_user)
    return templates.TemplateResponse(
        "admin/user_import.html",
        {"request": request, "current_user": current_user, "result": result},
    )


@router.get("/api/admin/users")
async def api_list_users(
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    result = await db.execute(select(DeptUser).order_by(DeptUser.user_no))
    users = result.scalars().all()
    return {"success": True, "data": {"users": [UserRead.model_validate(u) for u in users]}}


@router.post("/api/admin/users", status_code=status.HTTP_201_CREATED)
async def api_create_user(
    request: Request,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    user = await create_user(db, request, payload, current_user)
    return {"success": True, "data": {"user": UserRead.model_validate(user)}}


@router.put("/api/admin/users/{user_id}")
async def api_update_user(
    request: Request,
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    user = await update_user(db, request, user_id, payload, current_user)
    return {"success": True, "data": {"user": UserRead.model_validate(user)}}


@router.post("/api/admin/users/{user_id}/activate")
async def api_activate_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    user = await set_user_active(db, request, user_id, True, current_user)
    return {"success": True, "data": {"user": UserRead.model_validate(user)}}


@router.post("/api/admin/users/{user_id}/deactivate")
async def api_deactivate_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    user = await set_user_active(db, request, user_id, False, current_user)
    return {"success": True, "data": {"user": UserRead.model_validate(user)}}


@router.post("/api/admin/users/import")
async def api_import_users(
    request: Request,
    file: UploadFile = File(...),
    initial_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> JSONResponse:
    result = await import_users_from_csv(db, request, file, initial_password, current_user)
    return JSONResponse(content={"success": True, "data": result})


@router.delete("/api/admin/users/{user_id}")
async def api_delete_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DeptUser = Depends(require_admin),
) -> dict[str, object]:
    deleted_user = await delete_user(db, request, user_id, current_user)
    return {"success": True, "data": {"user": UserRead.model_validate(deleted_user)}}


async def create_user(
    db: AsyncSession,
    request: Request,
    payload: UserCreate,
    current_user: DeptUser,
) -> DeptUser:
    valid_from = normalize_datetime(payload.valid_from)
    valid_to = normalize_datetime(payload.valid_to)
    ensure_valid_period(valid_from, valid_to)
    existing = await find_user_by_login_id(db, payload.login_id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ログインIDが重複しています")

    user = DeptUser(
        user_id=payload.login_id,
        user_name=payload.display_name,
        password=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
        start_date=valid_from,
        end_date=valid_to,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await record_activity(
        db,
        request,
        "user_create",
        user=current_user,
        target_type="user",
        target_id=str(user.id),
    )
    return user


async def update_user(
    db: AsyncSession,
    request: Request,
    user_id: int,
    payload: UserUpdate,
    current_user: DeptUser,
) -> DeptUser:
    user = await find_user_by_no(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが存在しません")

    valid_from = (
        normalize_datetime(payload.valid_from)
        if payload.valid_from is not None
        else normalize_datetime(user.start_date)
    )
    valid_to = (
        normalize_datetime(payload.valid_to)
        if payload.valid_to is not None
        else normalize_datetime(user.end_date)
    )
    ensure_valid_period(valid_from, valid_to)

    if payload.display_name is not None:
        user.user_name = payload.display_name
    if payload.password is not None:
        user.password = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.valid_from is not None:
        user.start_date = valid_from
    if payload.valid_to is not None:
        user.end_date = valid_to
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await db.commit()
    await db.refresh(user)
    await record_activity(
        db,
        request,
        "user_update",
        user=current_user,
        target_type="user",
        target_id=str(user.id),
    )
    return user


async def set_user_active(
    db: AsyncSession,
    request: Request,
    user_id: int,
    is_active: bool,
    current_user: DeptUser,
) -> DeptUser:
    user = await find_user_by_no(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが存在しません")
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    await record_activity(
        db,
        request,
        "user_activate" if is_active else "user_deactivate",
        user=current_user,
        target_type="user",
        target_id=str(user.id),
    )
    return user


async def delete_user(
    db: AsyncSession,
    request: Request,
    user_id: int,
    current_user: DeptUser,
) -> DeptUser:
    user = await find_user_by_no(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが存在しません")
    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ログイン中の管理者は削除できません")
    if user.role == "admin":
        admin_count_result = await db.execute(
            select(func.count()).select_from(DeptUser).where(DeptUser.role == "admin", DeptUser.is_active.is_(True))
        )
        if admin_count_result.scalar_one() <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="最後の有効な管理者は削除できません")

    deleted_user = DeptUser(
        user_no=user.user_no,
        user_id=user.user_id,
        user_name=user.user_name,
        password=user.password,
        role=user.role,
        is_active=user.is_active,
        create_date=user.create_date,
        start_date=user.start_date,
        end_date=user.end_date,
    )
    await record_activity(
        db,
        request,
        "user_delete",
        user=current_user,
        target_type="user",
        target_id=user.user_id,
    )
    await db.execute(delete(AccessLog).where(AccessLog.user_id == user.user_id))
    await db.execute(delete(DownloadHistory).where(DownloadHistory.user_id == user.user_id))
    await db.delete(user)
    await db.commit()
    return deleted_user


async def import_users_from_csv(
    db: AsyncSession,
    request: Request,
    file: UploadFile,
    initial_password: str,
    current_user: DeptUser,
) -> dict[str, object]:
    if len(initial_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="初期パスワードは8文字以上です")

    raw = await file.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"login_id", "display_name", "valid_from", "valid_to"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV列が不足しています")

    created_count = 0
    skipped_count = 0
    errors: list[dict[str, object]] = []
    for row_number, row in enumerate(reader, start=2):
        login_id = (row.get("login_id") or "").strip()
        display_name = (row.get("display_name") or "").strip()
        try:
            if not login_id or not display_name:
                raise ValueError("login_id/display_name は必須です")
            valid_from = parse_csv_date((row.get("valid_from") or "").strip())
            valid_to = parse_csv_date((row.get("valid_to") or "").strip(), end_of_day=True)
            ensure_valid_period(valid_from, valid_to)
            existing = await find_user_by_login_id(db, login_id)
            if existing is not None:
                skipped_count += 1
                continue

            db.add(
                DeptUser(
                    user_id=login_id,
                    user_name=display_name,
                    password=hash_password(initial_password),
                    role="member",
                    is_active=True,
                    start_date=valid_from,
                    end_date=valid_to,
                )
            )
            created_count += 1
        except Exception as exc:
            errors.append({"row": row_number, "message": str(exc)})

    await db.commit()
    await record_activity(
        db,
        request,
        "user_import",
        user=current_user,
        target_type="user",
        target_id=None,
    )
    return {
        "created_count": created_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }
