import json
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import WEBAPP_URL

router = Router()

class WarehouseState(StatesGroup):
    waiting_for_problem_desc = State()

async def call_webapp_api(action: str, data: dict):
    if not WEBAPP_URL:
        return None
    payload = {
        "action": action,
        "data": data
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBAPP_URL, data=json.dumps(payload)) as response:
                if response.status == 200:
                    return await response.json()
    except Exception as e:
        print(f"Error calling {action}: {e}")
    return None

@router.callback_query(F.data.startswith("show_workers_"))
async def process_show_workers(callback: CallbackQuery):
    await callback.answer("Завантаження списку комірників...", show_alert=False)
    delivery_id = callback.data.replace("show_workers_", "")
    
    workers_kb = []
    try:
        employees = await call_webapp_api("get_employees", {})
        if employees and isinstance(employees.get("data"), list):
            for emp in employees["data"]:
                role = str(emp.get("Роль") or "").lower()
                if "комірник" in role or "склад" in role:
                    name = str(emp.get("ПІБ") or emp.get("Ім'я") or "").strip()
                    tg_id = str(emp.get("Telegram") or emp.get("Telegram_ID") or emp.get("Логін") or "").strip()
                    if name and tg_id:
                        workers_kb.append([InlineKeyboardButton(text=f"👷 {name}", callback_data=f"awh_{delivery_id}_{tg_id}")])
    except Exception as e:
        print(f"Error fetching workers: {e}")
        
    if not workers_kb:
        await callback.message.answer("⚠️ Не знайдено жодного комірника в таблиці.")
        return
        
    await callback.message.edit_text(
        callback.message.html_text + "\n\nОберіть комірника для призначення збірки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=workers_kb),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("awh_"))
async def process_warehouse_assign(callback: CallbackQuery):
    await callback.answer("Призначення комірника...", show_alert=False)
    # Instantly clear inline keyboard to prevent double clicks
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    data_body = callback.data[4:]
    if "_" in data_body:
        delivery_id, worker_id = data_body.rsplit("_", 1)
        
        result = await call_webapp_api("assign_warehouse_worker", {
            "deliveryId": delivery_id,
            "workerId": worker_id
        })
        
        if result and result.get("status") == "success":
            worker_name = worker_id
            if worker_id == "general":
                worker_name = "Будь-який комірник"
            elif worker_id == "6670847663":
                worker_name = "Сергій"
            elif worker_id == "5227085951":
                worker_name = "Приходько.О"
            elif worker_id == "5617387180":
                worker_name = "Бранько Анатолій"
            elif worker_id == "691693823":
                worker_name = "Коваленко Олексій"
            else:
                try:
                    employees = await call_webapp_api("get_employees", {})
                    if employees and isinstance(employees.get("data"), list):
                        for emp in employees["data"]:
                            tg = str(emp.get("Telegram") or emp.get("Telegram_ID") or "")
                            login = str(emp.get("Логін") or "")
                            pib = str(emp.get("ПІБ") or emp.get("Ім'я") or "")
                            if (tg and tg == worker_id) or (login and login == worker_id):
                                worker_name = pib or login
                                break
                except Exception as e:
                    print(f"Error fetching worker name: {e}")
            
            try:
                await callback.message.edit_text(callback.message.html_text + f"\n\n✅ <b>Призначено комірника:</b> {worker_name}", parse_mode="HTML")
            except Exception:
                await callback.message.answer(f"✅ <b>Призначено комірника:</b> {worker_name}", parse_mode="HTML")
        else:
            await callback.message.answer("❌ Помилка при призначенні комірника. Спробуйте ще раз.")
    else:
        await callback.answer("Невірні дані.")

@router.callback_query(F.data.startswith("wh_supplier_receive_"))
async def process_warehouse_supplier_receive(callback: CallbackQuery):
    await callback.answer("Прийомку товару зафіксовано!", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    delivery_id = callback.data.replace("wh_supplier_receive_", "")
    
    result = await call_webapp_api("update_status", {
        "id": delivery_id,
        "status": "Прийнято на склад",
        "comment": "Прийнято комірником на склад"
    })
    
    if result and result.get("status") == "success":
        try:
            await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Статус:</b> Прийнято на склад (закупівля завершена).", parse_mode="HTML")
        except Exception:
            await callback.message.answer("✅ <b>Статус:</b> Прийнято на склад (закупівля завершена).", parse_mode="HTML")
    else:
        await callback.message.answer("❌ Помилка оновлення статусу прийомки.")

@router.callback_query(F.data.startswith("wh_confirm_"))
async def process_warehouse_confirm(callback: CallbackQuery):
    await callback.answer("Замовлення відмічено як зібране!", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    delivery_id = callback.data.replace("wh_confirm_", "")
    worker_id = str(callback.from_user.id)
    worker_name = callback.from_user.full_name or callback.from_user.username or worker_id
    
    result = await call_webapp_api("update_warehouse_status", {
        "deliveryId": delivery_id,
        "status": "Зібрано",
        "workerId": worker_id,
        "workerName": worker_name
    })
    
    if result and result.get("status") == "success":
        car_id = result.get("car_id", "").strip().lower()
        if "самовивіз" in car_id:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Видано клієнту", callback_data=f"wh_delivered_{delivery_id}")],
                [InlineKeyboardButton(text="❌ Не зміг відвантажити", callback_data=f"wh_not_delivered_{delivery_id}")]
            ])
            await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Статус:</b> Скомплектовано (Самовивіз).\nКоли віддасте товар клієнту, натисніть кнопку нижче:", reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Статус:</b> Скомплектовано та готово до відвантаження машиною.", parse_mode="HTML")
    else:
        await callback.message.answer("❌ Помилка оновлення статусу збору.")

@router.callback_query(F.data.startswith("wh_delivered_"))
async def process_warehouse_delivered(callback: CallbackQuery):
    delivery_id = callback.data.replace("wh_delivered_", "")
    
    result = await call_webapp_api("update_status", {
        "id": delivery_id,
        "status": "Виконано",
        "comment": ""
    })
    
    if result and result.get("status") == "success":
        await callback.answer("Замовлення успішно відвантажено!", show_alert=True)
        original_text = callback.message.html_text.split("\n\n✅ <b>Статус:</b>")[0]
        await callback.message.edit_text(original_text + f"\n\n✅ <b>Статус:</b> Виконано (видано клієнту).", parse_mode="HTML")
    else:
        await callback.answer("Помилка оновлення статусу.", show_alert=True)

@router.callback_query(F.data.startswith("wh_not_delivered_"))
async def process_warehouse_not_delivered(callback: CallbackQuery):
    delivery_id = callback.data.replace("wh_not_delivered_", "")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Клієнт не приїхав", callback_data=f"wh_refusal_{delivery_id}_Клієнт не приїхав")],
        [InlineKeyboardButton(text="Клієнт відмовився", callback_data=f"wh_refusal_{delivery_id}_Клієнт відмовився")]
    ])
    
    original_text = callback.message.html_text.split("\n\nКоли віддасте товар")[0]
    await callback.message.edit_text(
        original_text + "\n\n⚠️ Вкажіть причину невідвантаження:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("wh_refusal_"))
async def process_warehouse_refusal(callback: CallbackQuery):
    # Format: wh_refusal_{delivery_id}_{reason}
    body = callback.data[len("wh_refusal_"):]
    underscore_pos = body.index("_")
    delivery_id = body[:underscore_pos]
    reason = body[underscore_pos + 1:]
    
    result = await call_webapp_api("update_warehouse_status", {
        "deliveryId": delivery_id,
        "status": f"Відмова: {reason}"
    })
    
    if result and result.get("status") == "success":
        await callback.answer("Статус відмови зафіксовано. Сповіщення надіслано.", show_alert=True)
        original_text = callback.message.html_text.split("\n\n⚠️ Вкажіть причину")[0]
        await callback.message.edit_text(original_text + f"\n\n⚠️ <b>Статус:</b> Відмова ({reason}).", parse_mode="HTML")
    else:
        await callback.answer("Помилка оновлення статусу.", show_alert=True)

@router.callback_query(F.data.startswith("wh_problem_"))
async def process_warehouse_problem(callback: CallbackQuery):
    delivery_id = callback.data.replace("wh_problem_", "")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Немає в наявності", callback_data=f"wh_reason_{delivery_id}_Немає в наявності")],
        [InlineKeyboardButton(text="⚠️ Бракований товар", callback_data=f"wh_reason_{delivery_id}_Бракований товар")],
        [InlineKeyboardButton(text="🔄 Невірна комплектація", callback_data=f"wh_reason_{delivery_id}_Невірна комплектація")],
        [InlineKeyboardButton(text="❓ Інше", callback_data=f"wh_reason_{delivery_id}_Інше")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wh_back_{delivery_id}")]
    ])
    
    await callback.message.edit_text(
        callback.message.html_text + "\n\n⚠️ Оберіть причину проблеми:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("wh_back_"))
async def process_warehouse_back(callback: CallbackQuery):
    delivery_id = callback.data.replace("wh_back_", "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити (Зібрано)", callback_data=f"wh_confirm_{delivery_id}")],
        [InlineKeyboardButton(text="⚠️ Проблема зі збіркою", callback_data=f"wh_problem_{delivery_id}")]
    ])
    original_text = callback.message.html_text.split("\n\n⚠️ Оберіть причину")[0]
    await callback.message.edit_text(original_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("wh_reason_"))
async def process_warehouse_reason(callback: CallbackQuery, state: FSMContext):
    # Format: wh_reason_{delivery_id}_{reason}
    # Strip prefix and split on first underscore only to get delivery_id
    body = callback.data[len("wh_reason_"):]  # e.g. "136_Немає в наявності"
    underscore_pos = body.index("_")
    delivery_id = body[:underscore_pos]
    reason = body[underscore_pos + 1:]
    
    if reason == "Інше":
        await state.update_data(delivery_id=delivery_id)
        await state.set_state(WarehouseState.waiting_for_problem_desc)
        await callback.message.edit_text("✍️ Будь ласка, напишіть детально суть проблеми текстом:")
        await callback.answer()
        return
        
    result = await call_webapp_api("update_warehouse_status", {
        "deliveryId": delivery_id,
        "status": f"Проблема: {reason}"
    })
    
    if result and result.get("status") == "success":
        await callback.answer("Проблему зафіксовано. Очікуйте.", show_alert=True)
        original_text = callback.message.html_text.split("\n\n⚠️ Оберіть причину")[0]
        await callback.message.edit_text(original_text + f"\n\n⚠️ <b>Статус:</b> Проблема ({reason}).", parse_mode="HTML")
    else:
        await callback.answer("Помилка оновлення статусу.", show_alert=True)

@router.message(WarehouseState.waiting_for_problem_desc)
async def process_custom_problem(message: Message, state: FSMContext):
    data = await state.get_data()
    delivery_id = data.get('delivery_id')
    reason = message.text
    
    result = await call_webapp_api("update_warehouse_status", {
        "deliveryId": delivery_id,
        "status": f"Проблема: {reason}"
    })
    
    if result and result.get("status") == "success":
        await message.answer("✅ Проблему успішно зафіксовано. Сповіщення надіслано.")
    else:
        await message.answer("❌ Помилка оновлення статусу.")
        
    await state.clear()
