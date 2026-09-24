import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.sheets import add_delivery_to_sheet, update_delivery_status_in_sheet, save_daily_crew_to_sheet

router = Router()

# Стейты для додавання доставки менеджером
class AddDeliveryStates(StatesGroup):
    waiting_for_order_num = State()
    waiting_for_payment = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_address = State()

# Стейты для підтвердження доставки водієм
class DriverStates(StatesGroup):
    waiting_for_location = State()
    waiting_for_custom_problem = State()

# --- МЕНЕДЖЕРСЬКИЙ ФЛОУ ---

@router.message(Command("add_delivery"))
async def cmd_add_delivery(message: Message, state: FSMContext):
    await message.answer("Вкажіть, будь ласка, номер замовлення:")
    await state.set_state(AddDeliveryStates.waiting_for_order_num)

@router.message(AddDeliveryStates.waiting_for_order_num)
async def process_order_num(message: Message, state: FSMContext):
    await state.update_data(order_num=message.text)
    
    payment_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплачено", callback_data="pay_full")],
        [InlineKeyboardButton(text="Оплачено частково", callback_data="pay_part")],
        [InlineKeyboardButton(text="Не оплачено", callback_data="pay_none")]
    ])
    
    await message.answer("Чи це замовлення оплачено?", reply_markup=payment_kb)
    await state.set_state(AddDeliveryStates.waiting_for_payment)

@router.callback_query(AddDeliveryStates.waiting_for_payment)
async def process_payment(callback: CallbackQuery, state: FSMContext):
    payment_status = ""
    if callback.data == "pay_full":
        payment_status = "Оплачено"
    elif callback.data == "pay_part":
        payment_status = "Оплачено частково"
    elif callback.data == "pay_none":
        payment_status = "Не оплачено"
        
    await state.update_data(payment=payment_status)
    await callback.message.edit_text(f"Статус оплати: {payment_status}\n\nТепер вкажіть дату доставки (напр. 18.05.2026):")
    await state.set_state(AddDeliveryStates.waiting_for_date)

@router.message(AddDeliveryStates.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("Вкажіть час доставки (напр. 10:00):")
    await state.set_state(AddDeliveryStates.waiting_for_time)

@router.message(AddDeliveryStates.waiting_for_time)
async def process_time(message: Message, state: FSMContext):
    await state.update_data(time=message.text)
    await message.answer("Вкажіть адресу доставки:")
    await state.set_state(AddDeliveryStates.waiting_for_address)

@router.message(AddDeliveryStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    data = await state.get_data()
    address = message.text
    
    delivery_data = {
        "driver_id": "1", # За замовчуванням
        "date": data['date'],
        "time": data['time'],
        "address": address,
        "order_num": data['order_num'],
        "payment": data['payment'],
        "manager_chat_id": str(message.chat.id),
        "comment": f"Замовлення №{data['order_num']}, Оплата: {data['payment']}"
    }
    
    result = await add_delivery_to_sheet(delivery_data)
    
    await state.clear()
    
    if result.get("status") == "success":
        await message.answer(f"✅ Доставку створено в таблиці!\n"
                             f"📦 Замовлення №: {data['order_num']}\n"
                             f"💰 Статус: {data['payment']}\n"
                             f"📅 Дата: {data['date']}\n"
                             f"🕒 Час: {data['time']}\n"
                             f"📍 Адреса: {address}")
    else:
        await message.answer(f"❌ Помилка при збереженні в таблицю: {result.get('message')}")

# --- ВОДІЙСЬКИЙ ФЛОУ ---

# Тестова команда для виклику меню вибору авто
@router.message(Command("test_car_selection"))
async def cmd_test_car_selection(message: Message):
    car_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Hyundai EX-8", callback_data="select_car_1")],
        [InlineKeyboardButton(text="MAN", callback_data="select_car_2")],
        [InlineKeyboardButton(text="Volkswagen Crafter", callback_data="select_car_3")],
        [InlineKeyboardButton(text="Renault Dokker", callback_data="select_car_4")]
    ])
    await message.answer("🔔 Тест! Оберіть, будь ласка, автомобіль, на якому ви працюватимете завтра:", reply_markup=car_kb)

# Обробка вибору авто
@router.callback_query(F.data.startswith("select_car_"))
async def process_car_selection(callback: CallbackQuery):
    car_id = callback.data.split("_")[2]
    chat_id = str(callback.message.chat.id)
    
    import json
    import os
    
    # Save choice to database/selected_cars.json
    choices = {}
    if os.path.exists("database/selected_cars.json"):
        try:
            with open("database/selected_cars.json", "r", encoding="utf-8") as f:
                choices = json.load(f)
        except Exception:
            pass
            
    choices[chat_id] = car_id
    os.makedirs("database", exist_ok=True)
    with open("database/selected_cars.json", "w", encoding="utf-8") as f:
        json.dump(choices, f, ensure_ascii=False, indent=2)
        
    # Async save daily shift to live Google Sheets database
    from datetime import datetime, timedelta
    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d.%m.%Y")
    driver_name = callback.from_user.full_name or callback.from_user.first_name or "Водій"
    
    try:
        await save_daily_crew_to_sheet(tomorrow_str, car_id, chat_id, driver_name)
    except Exception as e:
        print("Error saving shift to Google Sheet:", e)
        
    await callback.message.edit_text(f"✅ Ти обрав **Авто {car_id}** на завтра.\nОчікуй план поїздок о 18:00.")

@router.message(Command("test_schedule"))
async def cmd_test_schedule(message: Message):
    delivery_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити доставку", callback_data="confirm_mock_1"),
            InlineKeyboardButton(text="❌ Проблема", callback_data="problem_mock_1")
        ]
    ])
    
    await message.answer("📋 Твій розклад на сьогодні:\n\n"
                         "📍 Адреса: вул. Хрещатик, 1\n"
                         "🕒 Час: 10:00\n"
                         "📦 Замовлення №: 12345", 
                         reply_markup=delivery_kb)

@router.callback_query(F.data.startswith("supply_drive_"))
async def process_supply_drive(callback: CallbackQuery):
    delivery_id = callback.data[len("supply_drive_"):]
    await callback.answer("🚚 Статус оновлено: Виїхав до постачальника", show_alert=True)
    
    from services.sheets import update_delivery_status_in_sheet, log_event_to_sheet, get_employees_from_sheet
    driver_name = "Водій у Telegram-боті"
    try:
        employees = await get_employees_from_sheet()
        for emp in employees:
            tg_id = str(emp.get('Telegram_ID') or emp.get('Telegram') or emp.get('ID') or '').strip()
            if tg_id == str(callback.from_user.id):
                driver_name = emp.get('ПІБ') or emp.get("Ім'я") or driver_name
                break
    except Exception:
        pass

    await update_delivery_status_in_sheet(
        delivery_id=delivery_id,
        status="В процесі",
        comment=""
    )
    await log_event_to_sheet(
        delivery_id=delivery_id,
        event_title="🚚 Водій виїхав до постачальника",
        initiator_info=f"Водій: {driver_name}"
    )

    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 🚚 Виїхав до постачальника", callback_data="none")],
        [InlineKeyboardButton(text="📥 Забрав товар у постачальника", callback_data=f"supply_took_{delivery_id}")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        pass

@router.callback_query(F.data.startswith("supply_took_"))
async def process_supply_took(callback: CallbackQuery):
    delivery_id = callback.data[len("supply_took_"):]
    await callback.answer("📥 Статус оновлено: Забрав товар у постачальника. Склад сповіщено!", show_alert=True)

    from services.sheets import update_delivery_status_in_sheet, log_event_to_sheet, get_employees_from_sheet, get_deliveries_from_sheet
    
    driver_name = "Водій у Telegram-боті"
    try:
        employees = await get_employees_from_sheet()
        for emp in employees:
            tg_id = str(emp.get('Telegram_ID') or emp.get('Telegram') or emp.get('ID') or '').strip()
            if tg_id == str(callback.from_user.id):
                driver_name = emp.get('ПІБ') or emp.get("Ім'я") or driver_name
                break
    except Exception:
        pass

    # 1. Update status to 'Забрано у постачальника' and log timeline event #1
    await update_delivery_status_in_sheet(
        delivery_id=delivery_id,
        status="Забрано у постачальника",
        comment=""
    )
    await log_event_to_sheet(
        delivery_id=delivery_id,
        event_title="📥 Водій забрав товар у постачальника",
        initiator_info=f"Водій: {driver_name}"
    )

    # 2. Automatically notify Head Warehouse (Сергій) about incoming arrival + log timeline event #2
    head_tg = '6670847663'
    wh_msg = f"🏬 <b>Водій ({driver_name}) забрав товар у постачальника та прямує на склад!</b>\n\n" \
             f"📦 <b>Замовлення №:</b> {delivery_id}\n" \
             f"📋 Будь ласка, приготуйтеся до приймання товару складом за чек-листом."
    wh_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Прийняти товар складом (Чек-лист)", callback_data=f"wh_confirm_{delivery_id}")]
    ])
    try:
        dels = await get_deliveries_from_sheet()
        target_del = next((d for d in dels if str(d.get('ID')) == str(delivery_id)), None)
        hist = str(target_del.get('Історія_Операцій', '')) if target_del else ''
        if 'сповіщення на Склад про очікування товару' not in hist:
            await callback.bot.send_message(chat_id=head_tg, text=wh_msg, parse_mode="HTML", reply_markup=wh_kb)
            await log_event_to_sheet(
                delivery_id=delivery_id,
                event_title="🏬 Бот автоматично надіслав сповіщення на Склад про очікування товару від постачальника",
                initiator_info="Бот"
            )
    except Exception as ex:
        logging.error(f"Error sending supply arrival notice to head warehouse: {ex}")

    done_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Товар прийнято від постачальника", callback_data="none")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=done_kb)
    except Exception:
        pass

    # 3. Asynchronous 30-second delay -> Send notification to Ira Order (7797165411) + log timeline event #3
    async def send_ira_order_notice():
        await asyncio.sleep(30)
        ira_tg = '7797165411'
        order_num = str(delivery_id)
        supplier_address = "Постачальник"
        try:
            dels = await get_deliveries_from_sheet()
            target_del = next((d for d in dels if str(d.get('ID')) == str(delivery_id)), None)
            if target_del:
                order_num = target_del.get('Номер_замовлення') or order_num
                supplier_address = target_del.get('Адреса') or supplier_address
        except Exception:
            pass

        ira_msg = f"📥 <b>Водій забрав товар у постачальника!</b>\n\n" \
                  f"📦 <b>Замовлення №:</b> {order_num}\n" \
                  f"👤 <b>Водій:</b> {driver_name}\n" \
                  f"📍 <b>Адреса постачальника:</b> {supplier_address}"
        try:
            await callback.bot.send_message(chat_id=ira_tg, text=ira_msg, parse_mode="HTML")
            await log_event_to_sheet(
                delivery_id=delivery_id,
                event_title="📩 Бот автоматично надіслав сповіщення менеджеру Ірі Ордер про забір товару",
                initiator_info="Бот"
            )
            logging.info(f"30s delay: Sent Ira Order supply collection notice for delivery {delivery_id}")
        except Exception as ex:
            logging.error(f"Error sending 30s notice to Ira Order: {ex}")

    asyncio.create_task(send_ira_order_notice())

@router.callback_query(F.data.startswith("confirm_supplier_"))
async def process_confirm_supplier(callback: CallbackQuery, state: FSMContext):
    delivery_id = callback.data[len("confirm_supplier_"):]
    await state.update_data(
        confirming_delivery=delivery_id,
        is_supplier_pickup=True,
        delivery_message_id=callback.message.message_id
    )
    
    loc_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Надіслати геолокацію", request_location=True)]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await callback.message.answer("Для підтвердження забору товару у постачальника, будь ласка, надішліть вашу геолокацію:", reply_markup=loc_kb)
    await state.set_state(DriverStates.waiting_for_location)

@router.callback_query(F.data.startswith("view_invoice_"))
async def process_view_invoice(callback: CallbackQuery):
    delivery_id = callback.data[len("view_invoice_"):]
    from services.sheets import get_deliveries_from_sheet
    import config
    import json
    import requests

    try:
        deliveries = await get_deliveries_from_sheet()
        delivery_row = next((d for d in deliveries if str(d.get('ID')) == str(delivery_id)), None)
        invoice_url = delivery_row.get("Накладна_URL") or delivery_row.get("Накладна") if delivery_row else None
        
        if invoice_url:
            files_list = []
            try:
                if invoice_url.startswith("["):
                    files_list = json.loads(invoice_url)
                else:
                    files_list = [invoice_url]
            except Exception:
                files_list = [invoice_url]

            parsed_items_all = []
            
            for file_idx, f_url in enumerate(files_list):
                if f_url.startswith("data:image"):
                    import base64
                    header, base64_data = f_url.split(",", 1)
                    
                    # Attempt Gemini Vision OCR on image silently
                    if config.GEMINI_API_KEY:
                        try:
                            mime_type = "image/jpeg"
                            if "png" in header: mime_type = "image/png"
                            
                            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={config.GEMINI_API_KEY}"
                            prompt_text = (
                                "Розпізнай товарний чек або накладну 1С на зображенні. "
                                "Витягни перелік товарів та кількість. Поверни ТІЛЬКИ чистий JSON масив об'єктів у форматі: "
                                "[{\"item\": \"Труба 16х2\", \"qty\": \"100 м\"}]. Жодного markdown та пояснень."
                            )
                            payload = {
                                "contents": [{
                                    "parts": [
                                        {"text": prompt_text},
                                        {
                                            "inline_data": {
                                                "mime_type": mime_type,
                                                "data": base64_data
                                            }
                                        }
                                    ]
                                }]
                            }
                            res = requests.post(api_url, json=payload, timeout=10)
                            if res.status_code == 200:
                                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                                if raw_text.startswith("```"):
                                    raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                                items = json.loads(raw_text)
                                if isinstance(items, list):
                                    parsed_items_all.extend(items)
                        except Exception as ai_err:
                            print("Gemini Vision Invoice OCR Exception:", ai_err)

            # Render interactive checklist ONLY for driver with Fold/Unfold option
            if parsed_items_all:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                item_buttons = []
                for idx, it in enumerate(parsed_items_all):
                    item_name = it.get('item', 'Товар')
                    item_qty = it.get('qty', '')
                    btn_label = f"▫️ {item_name} — {item_qty}".strip()
                    item_buttons.append([InlineKeyboardButton(text=btn_label, callback_data=f"toggle_item_{delivery_id}_{idx}")])
                
                item_buttons.append([InlineKeyboardButton(text="✅ Підтвердити приймання", callback_data=f"confirm_{delivery_id}")])
                item_buttons.append([InlineKeyboardButton(text="🔼 Згорнути чек-лист", callback_data=f"fold_checklist_{delivery_id}")])
                checklist_kb = InlineKeyboardMarkup(inline_keyboard=item_buttons)
                
                await callback.message.answer(
                    f"📋 <b>Чек-лист товарів з 1С накладної (Замовлення №{delivery_id}):</b>\n"
                    "Відмічайте галочками прийнятий товар у постачальника:",
                    parse_mode="HTML",
                    reply_markup=checklist_kb
                )
            else:
                await callback.message.answer("⚠️ Не вдалося автоматично розпізнати список товарів з накладної.", parse_mode="HTML")
        else:
            await callback.answer("⚠️ Накладну не знайдено або файл відсутній.", show_alert=True)
    except Exception as e:
        await callback.answer("⚠️ Не вдалося відкрити накладну.", show_alert=True)

@router.callback_query(F.data.startswith("fold_checklist_"))
async def process_fold_checklist(callback: CallbackQuery):
    try:
        await callback.message.delete()
        await callback.answer("Чек-лист згорнуто. Ви можете відкрити його знову кнопкою 🔽", show_alert=False)
    except Exception as e:
        await callback.answer("Згорнуто.", show_alert=False)

@router.callback_query(F.data.startswith("toggle_item_"))
async def process_toggle_item(callback: CallbackQuery):
    try:
        # Data format: toggle_item_{del_id}_{item_idx}
        parts = callback.data.split("_")
        if len(parts) >= 4:
            del_id = parts[2]
            item_idx = int(parts[3])
            
            # Toggle button label visually between unchecked ▫️ and checked ✅
            reply_markup = callback.message.reply_markup
            if reply_markup and reply_markup.inline_keyboard:
                new_keyboard = []
                for row in reply_markup.inline_keyboard:
                    new_row = []
                    for btn in row:
                        if btn.callback_data == callback.data:
                            current_text = btn.text
                            if current_text.startswith("▫️"):
                                new_text = "✅ " + current_text[2:].strip() + " (Прийнято)"
                            elif current_text.startswith("✅"):
                                clean_text = current_text.replace("✅", "").replace("(Прийнято)", "").strip()
                                new_text = "▫️ " + clean_text
                            else:
                                new_text = "✅ " + current_text
                            new_row.append(InlineKeyboardButton(text=new_text, callback_data=btn.callback_data))
                        else:
                            new_row.append(btn)
                    new_keyboard.append(new_row)
                
                await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard))
                await callback.answer("Статус позиції змінено!")
                return
    except Exception as e:
        print("Error in process_toggle_item:", e)
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_"))
async def process_confirm(callback: CallbackQuery, state: FSMContext):
    delivery_id = callback.data[len("confirm_"):]
    await state.clear()
    
    # Extract list of accepted goods marked by driver if inline checklist was present
    accepted_items_list = []
    try:
        reply_markup = callback.message.reply_markup
        if reply_markup and reply_markup.inline_keyboard:
            for row in reply_markup.inline_keyboard:
                for btn in row:
                    if btn.text.startswith("✅") and "Прийнято" in btn.text:
                        clean_item = btn.text.replace("✅", "").replace("(Прийнято)", "").strip()
                        accepted_items_list.append(clean_item)
    except Exception as e:
        print("Error reading accepted items:", e)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        pass

    if str(delivery_id).startswith("mock_"):
        result = {"status": "success"}
    else:
        result = await update_delivery_status_in_sheet(
            delivery_id=delivery_id,
            status="Виконано",
            comment="Доставка успішно підтверджена водієм"
        )
        
    if result.get("status") == "success":
        await callback.message.answer(
            "✅ <b>Доставку успішно підтверджено!</b>\n"
            "Дякуємо! Статус оновлено у системі CRM.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await callback.answer("✅ Доставку підтверджено!", show_alert=False)

        # Notify Head Warehouse Worker & Manager (Ira Order) with accepted items list
        from services.sheets import get_deliveries_from_sheet
        try:
            deliveries = await get_deliveries_from_sheet()
            delivery_row = next((d for d in deliveries if str(d.get('ID')) == str(delivery_id)), None)
            
            if delivery_row:
                order_num = delivery_row.get("Номер_замовлення") or delivery_id
                manager_tg_id = delivery_row.get("ID_Менеджера") or delivery_row.get("Менеджер")
                driver_name = callback.from_user.full_name or callback.from_user.first_name or "Водій"

                items_text = "\n".join([f"  • ✅ {it}" for it in accepted_items_list]) if accepted_items_list else "  • Увесь товар за накладною 1С"
                
                report_message = (
                    f"📦 <b>ПРИЙНЯТТЯ ТОВАРУ У ПОСТАЧАЛЬНИКА ВИКОНАНО!</b>\n\n"
                    f"🔢 <b>Замовлення №:</b> {order_num}\n"
                    f"🚚 <b>Водій:</b> {driver_name}\n\n"
                    f"📋 <b>Прийняті позиції:</b>\n{items_text}\n\n"
                    f"🏬 <i>Товар везеться на склад Propex.</i>"
                )

                # Send notification to Manager Ira Order if ID is available
                if manager_tg_id:
                    try:
                        await callback.bot.send_message(chat_id=manager_tg_id, text=report_message, parse_mode="HTML")
                    except Exception as m_err:
                        print("Could not send report to manager:", m_err)
                
                # Also log for Head Warehouse Worker / Admin
                if config.ADMIN_ID and str(config.ADMIN_ID) != str(manager_tg_id):
                    try:
                        await callback.bot.send_message(chat_id=config.ADMIN_ID, text=report_message, parse_mode="HTML")
                    except Exception as a_err:
                        print("Could not send report to admin:", a_err)

        except Exception as notify_err:
            print("Error notifying warehouse/manager:", notify_err)
    else:
        await callback.answer("⚠️ Не вдалося оновити статус у таблиці.", show_alert=True)

@router.message(DriverStates.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    import logging
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    from services.sheets import get_deliveries_from_sheet

    data = await state.get_data()
    delivery_id = data.get('confirming_delivery')
    delivery_message_id = data.get('delivery_message_id')

    lat = message.location.latitude
    lon = message.location.longitude
    driver_coords = (lat, lon)

    # --- Дані про mock-доставки (адреси мають збігатися з тим, що надсилається водіям) ---
    MOCK_ADDRESSES = {
        "mock_1": "вул. Хрещатик, 1, Київ",
        "mock_2": "вул. Банкова, 2, Київ",
    }

    # --- Визначаємо адресу доставки ---
    delivery_address = None

    if str(delivery_id).startswith("mock_"):
        delivery_address = MOCK_ADDRESSES.get(str(delivery_id))
    else:
        try:
            deliveries = await get_deliveries_from_sheet()
            delivery_row = next((d for d in deliveries if str(d.get('ID')) == str(delivery_id)), None)
            if delivery_row:
                delivery_address = delivery_row.get("Адреса")
        except Exception as e:
            logging.error(f"Error fetching delivery from sheet: {e}")

    # --- Якщо адресу взагалі не вдалося знайти — блокуємо підтвердження ---
    if not delivery_address:
        await state.clear()
        await message.answer(
            "⚠️ Не вдалося визначити адресу доставки для перевірки геолокації.\n"
            "Будь ласка, зателефонуйте менеджеру для ручного підтвердження.",
            reply_markup=ReplyKeyboardMarkup(keyboard=[], remove_keyboard=True)
        )
        return

    # --- Обов'язкова геолокаційна перевірка ---
    try:
        geolocator = Nominatim(user_agent="propex_delivery_bot")
        search_query = (
            delivery_address
            if ("київ" in delivery_address.lower() or "киев" in delivery_address.lower())
            else "Київ, " + delivery_address
        )

        geo_location = geolocator.geocode(search_query, timeout=10)

        if geo_location is None:
            # Геолокація не знайдена — блокуємо підтвердження
            await message.answer(
                f"⚠️ Не вдалося знайти адресу «{delivery_address}» на карті.\n"
                "Підтвердження доставки заблоковано. Зверніться до менеджера.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📍 Надіслати геолокацію", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
            return

        target_coords = (geo_location.latitude, geo_location.longitude)
        distance_meters = geodesic(driver_coords, target_coords).meters
        
        logging.info(f"GEOLOCATION CHECK: Driver {driver_coords} vs Target {target_coords} ({delivery_address}) = {distance_meters}m")

        if distance_meters > 1000:
            await message.answer(
                f"❌ Ви знаходитесь занадто далеко від адреси!\n\n"
                f"📍 Адреса доставки: {delivery_address}\n"
                f"📏 Ваша відстань: {int(distance_meters)} м\n"
                f"✅ Допустима відстань: до 1 км\n\n"
                "Підтвердіть доставку, перебуваючи безпосередньо за адресою клієнта.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📍 Надіслати геолокацію", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
            return  # НЕ підтверджуємо доставку

    except Exception as e:
        logging.error(f"Geocoding validation error: {e}")
        # При будь-якій помилці геолокації — НЕ підтверджуємо, просимо повторити
        await message.answer(
            "⚠️ Помилка перевірки геолокації. Будь ласка, надішліть геолокацію ще раз.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📍 Надіслати геолокацію", request_location=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return

    is_supplier_pickup = data.get('is_supplier_pickup', False)

    # --- Геолокація підтверджена — оновлюємо статус ---
    await state.clear()
    
    if delivery_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=delivery_message_id,
                reply_markup=None
            )
        except Exception as e:
            logging.error(f"Failed to remove markup from delivery message: {e}")

    if str(delivery_id).startswith("mock_"):
        mock_data = {
            "mock_1": {
                "id": "mock_1", "car_id": "2", "date": "today",
                "time": "10:00", "address": "вул. Хрещатик, 1, Київ",
                "order_num": "77701", "payment": "Оплачено",
                "receiver_name": "Іван Коваленко", "receiver_phone": "+380671112233",
                "manager_chat_id": str(message.chat.id)
            },
            "mock_2": {
                "id": "mock_2", "car_id": "2", "date": "today",
                "time": "12:00", "address": "вул. Банкова, 2, Київ",
                "order_num": "77702", "payment": "Не оплачено",
                "receiver_name": "Олена Петренко", "receiver_phone": "+380674445566",
                "manager_chat_id": str(message.chat.id)
            }
        }
        mock_delivery = mock_data.get(str(delivery_id), {
            "id": delivery_id, "car_id": "1", "date": "today", "time": "12:00",
            "address": delivery_address, "order_num": "99999", "payment": "Не оплачено",
            "receiver_name": "Тестовий Отримувач", "receiver_phone": "+380000000000",
            "manager_chat_id": str(message.chat.id)
        })
        result = {"status": "success", "delivery": mock_delivery}
    else:
        new_status = "Забрано у постачальника" if is_supplier_pickup else "Виконано"
        status_comment = "Товар успішно заборано від постачальника" if is_supplier_pickup else "Доставка успішно підтверджена"
        result = await update_delivery_status_in_sheet(
            delivery_id=delivery_id,
            status=new_status,
            comment=status_comment
        )
        
    if is_supplier_pickup:
        await message.answer(
            "✅ Геолокація підтверджена!\n"
            "Статус успішно змінено на «Забрано у постачальника».\n"
            "Сповіщення про очікуваний приїзд надіслано головному комірнику склада! 🏬",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer(
            "✅ Геолокація підтверджена!\n"
            "Статус замовлення успішно змінено на «Виконано».",
            reply_markup=ReplyKeyboardRemove()
        )

@router.callback_query(F.data.startswith("problem_"))
async def process_problem(callback: CallbackQuery, state: FSMContext):
    delivery_id = callback.data[len("problem_"):]
    
    await state.update_data(problem_delivery_id=delivery_id)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    prob_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Зламалося авто", callback_data=f"probopt_car_{delivery_id}")],
        [InlineKeyboardButton(text="🚨 Повітряна тривога / В укриття", callback_data=f"probopt_alert_{delivery_id}")],
        [InlineKeyboardButton(text="👤 Клієнт не відповідає", callback_data=f"probopt_client_{delivery_id}")],
        [InlineKeyboardButton(text="📍 Не можу знайти адресу", callback_data=f"probopt_address_{delivery_id}")],
        [InlineKeyboardButton(text="✏️ Інша проблема (описати)...", callback_data=f"probopt_custom_{delivery_id}")]
    ])
    
    await callback.message.answer(
        f"🚨 Ви вказали, що виникла проблема з доставкою №{delivery_id}.\n"
        f"Оберіть, будь ласка, причину проблеми:",
        reply_markup=prob_kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("probopt_"))
async def process_problem_option(callback: CallbackQuery, state: FSMContext):
    # callback.data format: "probopt_{opt}_{delivery_id}"
    # delivery_id can contain underscores (e.g. mock_1), so split only first 2
    after_prefix = callback.data[len("probopt_"):]  # "car_mock_1" or "car_12345"
    underscore_idx = after_prefix.index("_")
    opt = after_prefix[:underscore_idx]             # "car"
    delivery_id = after_prefix[underscore_idx + 1:]  # "mock_1" or "12345"
    
    reason = ""
    if opt == "car":
        reason = "🚗 Зламався автомобіль"
    elif opt == "alert":
        reason = "🚨 Повітряна тривога / Прямую в укриття"
    elif opt == "client":
        reason = "👤 Клієнт не виходить на зв'язок"
    elif opt == "address":
        reason = "📍 Водій не може знайти адресу"
    elif opt == "custom":
        await state.update_data(custom_delivery_id=delivery_id)
        await state.set_state(DriverStates.waiting_for_custom_problem)
        await callback.message.answer("Будь ласка, введіть опис проблеми у текстовому повідомленні:")
        await callback.answer()
        return
        
    await state.clear()

    # Mock-доставки не зберігаються в Google Sheets — симулюємо успіх
    if str(delivery_id).startswith("mock_"):
        result = {"status": "success"}
    else:
        result = await update_delivery_status_in_sheet(
            delivery_id=delivery_id,
            status="Проблема",
            comment=reason
        )

    if result.get("status") == "success":
        await callback.message.edit_text(
            f"🚨 Повідомлено про проблему: <b>{reason}</b> (доставка №{delivery_id}).\n"
            f"Менеджер отримав екстрене сповіщення в Telegram.",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"⚠️ Помилка оновлення таблиці: {result.get('message')}.\n"
            f"Будь ласка, зателефонуйте менеджеру особисто!"
        )
    await callback.answer()

@router.message(DriverStates.waiting_for_custom_problem)
async def process_custom_problem(message: Message, state: FSMContext):
    data = await state.get_data()
    delivery_id = data.get('custom_delivery_id')
    reason = f"✏️ {message.text}"
    
    await state.clear()

    # Mock-доставки не зберігаються в Google Sheets — симулюємо успіх
    if str(delivery_id).startswith("mock_"):
        result = {"status": "success"}
    else:
        result = await update_delivery_status_in_sheet(
            delivery_id=delivery_id,
            status="Проблема",
            comment=reason
        )

    if result.get("status") == "success":
        await message.answer(
            f"🚨 Повідомлено про проблему: <b>{reason}</b> (доставка №{delivery_id}).\n"
            f"Менеджер отримав екстрене сповіщення в Telegram.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"⚠️ Помилка оновлення таблиці: {result.get('message')}.\n"
            f"Будь ласка, зателефонуйте менеджеру особисто!"
        )
