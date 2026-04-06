from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TELEGRAM_TOKEN
from config import ALLOWED_USER_ID
from modules.ai import chat as ai_chat, quick_insight
from modules.stocks import get_price, get_news
from modules.reminders import (
    add_todo, list_todos, complete_todo, complete_todos_bulk,
    add_scheduled_prompt, list_scheduled_prompts,
    toggle_scheduled_prompt, delete_scheduled_prompt,
    get_due_prompts, mark_prompt_run,
)
from modules.watchlist import add_stock, remove_stock, list_stocks
from modules.agents import (
    create_agent, agent_exists, get_agent,
    set_agent_schedule, toggle_agent, mark_agent_run,
    list_agents, save_to_memory, get_memory, get_due_agents,
    delete_agent,
)
from modules.injector import resolve_tags



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your assistant bot, Reyes V2.\n\n"
        "Commands:\n"
        "/start - This message\n"
        "/chat <text> - Chat with AI\n"
        "/stock <symbol> - Stock price\n"
        "/todo add <task> | /todo list | /todo done <id> | /todo done <start>-<end> - Manage todos\n"
        "/schedule <freq> <HH:MM> <name> | <prompt> - Schedule a Claude prompt\n"
        "/schedules - List scheduled prompts\n"
        "/scheduletoggle <id> - Pause or resume a prompt\n"
        "/scheduledel <id> - Delete a scheduled prompt\n"
        "/create <agentname> - Create a new agent\n"
        "/scheduleadv <agent> <freq> <HH:MM> <taskname> | <prompt> - Schedule an agent with advanced tags\n"
        "/agents - List your agents\n"
        "/agenttoggle <agentname> - Pause or resume an agent\n"
        "/agentmemory <agentname> - Show recent memory of an agent\n"
        "/agentdel <agentname> - Delete an agent and its memory\n"
        "/stockwatch add <TICKER> <shares> <avg_price> - Add stock to watchlist\n"
        "/stockwatch remove <TICKER> - Remove stock from watchlist\n"
        "/stockwatch list - Show watchlist with live P&L\n"
        "In your prompts, use &&STOCKWATCH&& to inject live stock data, &&TODOS&& for your todo list, or &&agentname&& to read an agent's memory."
    )


async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("Type something after /chat")
        return
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    reply = ai_chat(message)
    await update.message.reply_text(reply)


async def stock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /stock AAPL")
        return
    ticker = context.args[0]
    data = get_price(ticker)
    if not data:
        await update.message.reply_text("Ticker not found.")
        return
    if "error" in data:
        await update.message.reply_text(f"Error fetching data: {data['error']}")
        return

    lines = [
        f"{data['name']} ({data['ticker']})",
        f"Price: {data['currency']} {data['price']}",
    ]
    if data.get("day_low") and data.get("day_high"):
        lines.append(f"Day Range: {data['day_low']} - {data['day_high']}")
    if data.get("week52_low") and data.get("week52_high"):
        lines.append(f"52W Range: {data['week52_low']} - {data['week52_high']}")
    lines.append(f"Market Cap: {data['market_cap']}")
    lines.append(f"P/E Ratio: {data['pe_ratio']}")

    news = get_news(ticker)
    if news:
        lines.append("\nLatest News")
        for i, n in enumerate(news, 1):
            lines.append(f"{i}. {n['headline']}\n   {n['source']} · {n['date']}\n   {n['url']}")

    await update.message.reply_text("\n".join(lines))


async def todo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("/todo add <task> | /todo list | /todo done <id> | /todo done <start>-<end>")
        return

    sub = args[0].lower()

    if sub == "add":
        task = " ".join(args[1:])
        item = add_todo(task)
        await update.message.reply_text(f"Added task [{item['id']}]: {task}")

    elif sub == "list":
        todos = list_todos()
        if not todos:
            await update.message.reply_text("No pending tasks!")
        else:
            text = "\n".join(f"[{t['id']}] {t['task']}" for t in todos)
            await update.message.reply_text(text)

    elif sub == "done":
        arg = args[1]
        if "-" in arg:
            start, end = arg.split("-", 1)
            ids = list(range(int(start), int(end) + 1))
            completed, not_found = complete_todos_bulk(ids)
            parts = []
            if completed:
                parts.append(f"Done: {', '.join(str(i) for i in completed)}")
            if not_found:
                parts.append(f"Not found: {', '.join(str(i) for i in not_found)}")
            await update.message.reply_text("\n".join(parts) or "Nothing to do.")
        else:
            ok = complete_todo(int(arg))
            await update.message.reply_text("Done!" if ok else "Task not found.")


# ── Scheduled Prompts ─────────────────────────────────────

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)

    if "|" not in args:
        await update.message.reply_text(
            "Usage: /schedule <frequency> <HH:MM> <name> | <prompt>\n\n"
            "Examples:\n"
            "/schedule daily 08:00 Morning Quote | Give me an inspiring quote\n"
            "/schedule weekly:mon 09:00 Weekly Plan | Write my weekly plan\n"
            "/schedule weekly:fri 17:00 Week Review | Summarise my week\n\n"
            "Frequencies: daily, weekly:mon, weekly:tue ... weekly:sun"
        )
        return

    left, prompt = args.split("|", 1)
    left_parts   = left.strip().split()

    if len(left_parts) < 3:
        await update.message.reply_text("Include frequency, time, and a name before the |")
        return

    frequency = left_parts[0].lower()       # e.g. "daily" or "weekly:mon"
    time_str  = left_parts[1]               # e.g. "09:00"
    name      = " ".join(left_parts[2:])    # e.g. "Morning Quote"
    prompt    = prompt.strip()              # the actual Claude prompt

    valid_days = ["mon","tue","wed","thu","fri","sat","sun"]
    if frequency != "daily" and not any(frequency == f"weekly:{d}" for d in valid_days):
        await update.message.reply_text("Frequency must be 'daily' or 'weekly:mon' etc.")
        return

    item = add_scheduled_prompt(name, prompt, time_str, frequency)

    if item is None:
        await update.message.reply_text("Invalid time format. Use HH:MM e.g. 09:00")
        return

    await update.message.reply_text(
        f"Scheduled prompt [{item['id']}] created!\n\n"
        f"Name: {item['name']}\n"
        f"Time: {item['schedule']} ({item['frequency']})\n"
        f"Prompt: {item['prompt']}"
    )


async def schedules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompts = list_scheduled_prompts()

    if not prompts:
        await update.message.reply_text("No scheduled prompts yet.\nUse /schedule to create one.")
        return

    lines = ["Scheduled Prompts\n"]
    for p in prompts:
        status   = "ON" if p["enabled"] else "OFF"
        last_run = p["last_run"] or "Never"
        preview  = p["prompt"][:60] + ("..." if len(p["prompt"]) > 60 else "")
        lines.append(
            f"[{p['id']}] {p['name']} — {status}\n"
            f"  Time: {p['schedule']} | {p['frequency']}\n"
            f"  Prompt: {preview}\n"
            f"  Last run: {last_run}\n"
        )

    await update.message.reply_text("\n".join(lines))


async def schedule_toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /scheduletoggle <id>")
        return

    new_state = toggle_scheduled_prompt(int(context.args[0]))

    if new_state is None:
        await update.message.reply_text("No scheduled prompt found with that ID.")
        return

    state_text = "resumed" if new_state else "paused"
    await update.message.reply_text(f"Scheduled prompt [{context.args[0]}] {state_text}.")


async def schedule_del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /scheduledel <id>")
        return

    ok = delete_scheduled_prompt(int(context.args[0]))
    await update.message.reply_text(
        f"Deleted scheduled prompt [{context.args[0]}]." if ok else "Not found."
    )

# ── /stockwatch ───────────────────────────────────────────

async def stockwatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stockwatch add AAPL 10 185.50
    /stockwatch remove AAPL
    /stockwatch list
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "`/stockwatch add AAPL 10 185.50`\n"
            "`/stockwatch remove AAPL`\n"
            "`/stockwatch list`",
            parse_mode="Markdown"
        )
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: `/stockwatch add AAPL 10 185.50`",
                parse_mode="Markdown"
            )
            return
        try:
            ticker    = args[1].upper()
            shares    = float(args[2])
            avg_price = float(args[3])
        except ValueError:
            await update.message.reply_text("Shares and price must be numbers.")
            return
        add_stock(ticker, shares, avg_price)
        await update.message.reply_text(
            f"Added `{ticker}` — {shares} shares @ ${avg_price}",
            parse_mode="Markdown"
        )

    elif sub == "remove":
        if len(args) < 2:
            await update.message.reply_text("Usage: `/stockwatch remove AAPL`", parse_mode="Markdown")
            return
        ok = remove_stock(args[1])
        await update.message.reply_text(
            f"Removed `{args[1].upper()}`" if ok else "Not found.",
            parse_mode="Markdown"
        )

    elif sub == "list":
        stocks = list_stocks()
        if not stocks:
            await update.message.reply_text("Watchlist empty.")
            return
        lines = ["*Stock Watchlist*\n"]
        for s in stocks:
            lines.append(f"• `{s['ticker']}` — {s['shares']} shares @ ${s['avg_price']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /create ───────────────────────────────────────────────

async def create_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /create agent1  → creates a new agent called agent1
    """
    if not context.args:
        await update.message.reply_text("Usage: `/create <agentname>`", parse_mode="Markdown")
        return

    name   = context.args[0].lower()
    result = create_agent(name)

    if result is None:
        await update.message.reply_text(
            f"Agent `{name}` already exists.\n"
            f"Set its schedule with `/scheduleadv {name} 08:00 TaskName | your prompt`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"✅ Agent `{name}` created!\n\n"
        f"Now set its task:\n"
        f"`/scheduleadv {name} 08:00 TaskName | Your prompt here. Use **STOCKWATCH** to inject live stock data.`",
        parse_mode="Markdown"
    )


# ── /scheduleadv ──────────────────────────────────────────

async def scheduleadv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /scheduleadv agent1 daily 08:00 TaskName | Prompt with &&STOCKWATCH&&

    Frequency options: daily, weekly:mon ... weekly:sun
    Tag options in prompt:
      &&STOCKWATCH&&  → live portfolio data
      &&TODOS&&       → your todo list
      &&agent1&&      → agent1's memory
    """
    raw = " ".join(context.args)

    if "|" not in raw:
        await update.message.reply_text(
            "Usage: `/scheduleadv <agent> <freq> <HH:MM> <taskname> | <prompt>`\n\n"
            "Example:\n"
            "`/scheduleadv agent1 daily 08:00 InvestorReport | "
            "You are a Senior Bank Investor. Analyse &&STOCKWATCH&& "
            "and give a buy/hold/sell verdict for each stock.`",
            parse_mode="Markdown"
        )
        return

    left, prompt = raw.split("|", 1)
    parts        = left.strip().split()

    if len(parts) < 4:
        await update.message.reply_text(
            "Need: agent name, frequency, time, and task name before the `|`",
            parse_mode="Markdown"
        )
        return

    agent_name = parts[0].lower()
    frequency  = parts[1].lower()
    time_str   = parts[2]
    task_name  = " ".join(parts[3:])
    prompt     = prompt.strip()

    if not agent_exists(agent_name):
        await update.message.reply_text(
            f"Agent `{agent_name}` doesn't exist. Create it first with `/create {agent_name}`",
            parse_mode="Markdown"
        )
        return

    valid_days = ["mon","tue","wed","thu","fri","sat","sun"]
    if frequency != "daily" and not any(frequency == f"weekly:{d}" for d in valid_days):
        await update.message.reply_text(
            "Frequency must be `daily` or `weekly:mon` etc.",
            parse_mode="Markdown"
        )
        return

    try:
        from datetime import datetime
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("Invalid time. Use HH:MM e.g. `08:00`", parse_mode="Markdown")
        return

    set_agent_schedule(agent_name, time_str, frequency, task_name, prompt)

    await update.message.reply_text(
        f"Agent `{agent_name}` scheduled!\n\n"
        f"Task: {task_name}\n"
        f"Time: {time_str} ({frequency})\n"
        f"Prompt preview: _{prompt[:100]}..._\n\n"
        f"Toggle on/off: `/agenttoggle {agent_name}`",
        parse_mode="Markdown"
    )


# ── /agents ───────────────────────────────────────────────

async def agents_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/agents — list all agents and their status"""
    agents = list_agents()
    if not agents:
        await update.message.reply_text("No agents yet. Create one with `/create agent1`", parse_mode="Markdown")
        return

    lines = ["*Your Agents*\n"]
    for a in agents:
        status   = "ON" if a["enabled"] else "⏸️ OFF"
        schedule = f"{a['schedule']} ({a['frequency']})" if a["schedule"] else "No schedule set"
        last_run = a["last_run"] or "Never"
        lines.append(
            f"{status} `{a['name']}`\n"
            f"   {schedule}\n"
            f"   {a['task_name'] or 'No task'}\n"
            f"   Last run: {last_run}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /agenttoggle ──────────────────────────────────────────

async def agenttoggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/agenttoggle agent1 — pause or resume an agent"""
    if not context.args:
        await update.message.reply_text("Usage: `/agenttoggle <agentname>`", parse_mode="Markdown")
        return

    name      = context.args[0].lower()
    new_state = toggle_agent(name)

    if new_state is None:
        await update.message.reply_text(f"Agent `{name}` not found.", parse_mode="Markdown")
        return

    status = "resumed ✅" if new_state else "paused ⏸️"
    await update.message.reply_text(f"Agent `{name}` {status}", parse_mode="Markdown")


# ── /agentdel ─────────────────────────────────────────────

async def agentdel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/agentdel agent1 — permanently delete an agent and its memory"""
    if not context.args:
        await update.message.reply_text("Usage: `/agentdel <agentname>`", parse_mode="Markdown")
        return

    name = context.args[0].lower()
    ok   = delete_agent(name)

    if not ok:
        await update.message.reply_text(f"Agent `{name}` not found.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"Agent `{name}` deleted.", parse_mode="Markdown")


# ── /agentmemory ──────────────────────────────────────────

async def agentmemory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/agentmemory agent1 — show last 5 memory entries"""
    if not context.args:
        await update.message.reply_text("Usage: `/agentmemory <agentname>`", parse_mode="Markdown")
        return

    name    = context.args[0].lower()
    entries = get_memory(name, limit=5)

    if not entries:
        await update.message.reply_text(f"No memory yet for agent `{name}`", parse_mode="Markdown")
        return

    lines = [f"🧠 *Memory: {name}*\n"]
    for e in entries:
        lines.append(f"📅 _{e['date']}_\n{e['content']}\n")

    await send_long_message(context.bot, update.effective_chat.id, "\n".join(lines))
    
# ── Background jobs ───────────────────────────────────────

async def morning_summary(bot):
    todos = list_todos()
    count = len(todos)
    await bot.send_message(
        chat_id=ALLOWED_USER_ID,
        text=f"Good morning! You have {count} pending tasks today."
    )


async def run_scheduled_prompts(bot):
    """
    Runs every minute. Checks if any saved Claude prompts are due,
    calls Claude with the stored prompt, and sends the reply to you.
    """
    due = get_due_prompts()
    for item in due:
        try:
            # Which prompt is firing
            await bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"Scheduled: {item['name']}"
            )
            # Call Claude with the stored prompt
            response = quick_insight(item["prompt"], max_tokens=2500)
            await send_long_message(bot, ALLOWED_USER_ID, response)
            # Mark it as run so it doesn't fire again today
            mark_prompt_run(item["id"])
        except Exception as e:
            await bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"Scheduled prompt [{item['id']}] failed: {e}"
            )

async def send_long_message(bot, chat_id: int, text: str) -> None:
    """Split text into ≤4096-char chunks and send each as a separate message."""
    if not text or not text.strip():
        await bot.send_message(chat_id=chat_id, text="[No output produced]")
        return
    limit = 4096
    for i in range(0, len(text), limit):
        await bot.send_message(chat_id=chat_id, text=text[i:i + limit])


async def run_agents(bot) -> None:
    """Every minute — check if any agents are due to run."""
    due = get_due_agents()
    for agent in due:
        try:
            resolved_prompt = resolve_tags(agent["prompt"])

            await bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"*Agent {agent['name']} — {agent['task_name']}*",
                parse_mode="Markdown"
            )

            response = quick_insight(resolved_prompt, max_tokens=2500)

            await send_long_message(bot, ALLOWED_USER_ID, response)

            save_to_memory(agent["name"], response)
            mark_agent_run(agent["name"])

        except Exception as e:
            await bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"Agent {agent['name']} failed: {e}"
            )

# ── App setup ─────────────────────────────────────────────

async def post_init(application):
    scheduler = AsyncIOScheduler(timezone="Asia/Singapore")

    # your existing jobs are already here
    scheduler.add_job(
        morning_summary,
        trigger="cron",
        hour=8,
        minute=0,
        kwargs={"bot": application.bot}
    )

    scheduler.add_job(
        run_scheduled_prompts,
        trigger="interval",
        minutes=1,
        kwargs={"bot": application.bot}
    )

    # ← add this new job here
    scheduler.add_job(
        run_agents,
        trigger="interval",
        minutes=1,
        kwargs={"bot": application.bot},
        id="agent_runner",
    )

    scheduler.start()


app = Application.builder().token(TELEGRAM_TOKEN).build()
app.post_init = post_init

app.add_handler(CommandHandler("start",          start))
app.add_handler(CommandHandler("chat",           chat_cmd))
app.add_handler(CommandHandler("stock",          stock_cmd))
app.add_handler(CommandHandler("todo",           todo_cmd))
app.add_handler(CommandHandler("schedule",       schedule_cmd))
app.add_handler(CommandHandler("schedules",      schedules_cmd))
app.add_handler(CommandHandler("scheduletoggle", schedule_toggle_cmd))
app.add_handler(CommandHandler("scheduledel",    schedule_del_cmd))
app.add_handler(CommandHandler("stockwatch",   stockwatch_cmd))
app.add_handler(CommandHandler("create",       create_cmd))
app.add_handler(CommandHandler("scheduleadv",  scheduleadv_cmd))
app.add_handler(CommandHandler("agents",       agents_cmd))
app.add_handler(CommandHandler("agenttoggle",  agenttoggle_cmd))
app.add_handler(CommandHandler("agentdel",     agentdel_cmd))
app.add_handler(CommandHandler("agentmemory",  agentmemory_cmd))

app.run_polling()