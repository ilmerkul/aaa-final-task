#!/usr/bin/env python

"""
Bot for playing tic tac toe game with multiple CallbackQueryHandlers.
"""
import asyncio
import logging
import os
import random
from typing import Hashable

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Message,
                      Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler)

from utils import TicTacToe

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logging.getLogger('httpx').setLevel(logging.WARNING)


class SearchPlayerEvent:
    def __init__(self, chat_id=None):
        self.event = asyncio.Event()
        self.chat_id = chat_id
        self.room_hash = None

    async def wait(self):
        await self.event.wait()

    def set(self):
        self.event.set()


class MoveEvent:
    def __init__(self):
        self.event = asyncio.Event()
        self.turn_coord = None

    async def wait(self):
        await self.event.wait()

    def set(self):
        self.event.set()

    def clear(self):
        self.event.clear()

    def is_set(self) -> bool:
        return self.event.is_set()


class App:
    CONTINUE_GAME, FINISH_GAME = range(2)

    TOKEN = os.getenv('TG_TOKEN')

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.app_loop = asyncio.new_event_loop()

        self.application = Application.builder().token(self.TOKEN).build()
        self.tic_tac_toe = TicTacToe()

        self.player_queue = asyncio.Queue()
        self.worker_queue = asyncio.Queue()

        self.rooms = {}
        self.rooms_lock = asyncio.Lock()

    def generate_keyboard(self, state: list[list[str]]) \
            -> list[list[InlineKeyboardButton]]:
        """Generate tic tac toe keyboard 3x3 (telegram buttons)"""
        return [
            [
                InlineKeyboardButton(state[r][c], callback_data=f'{r}{c}')
                for r in range(3)
            ]
            for c in range(3)
        ]

    async def start_worker(self, update: Update,
                           context: ContextTypes.DEFAULT_TYPE,
                           ev: SearchPlayerEvent):
        await ev.wait()

        context.user_data[
            'keyboard_state'] = self.tic_tac_toe.get_default_state()
        context.user_data['room_hash'] = ev.room_hash
        keyboard = self.generate_keyboard(context.user_data['keyboard_state'])
        reply_markup = InlineKeyboardMarkup(keyboard)

        async with self.rooms_lock:
            rooms_data = self.rooms[ev.room_hash]

        symbol = rooms_data[update.message.chat.id]['symbol']

        m: Message = await update.message.reply_text(f'you {symbol}',
                                                     reply_markup=reply_markup)

        move_event = rooms_data['move_event']
        if not rooms_data[update.message.chat.id]['turn']:
            game_worker_task = asyncio.create_task(self.game_worker(m,
                                                                    context,
                                                                    move_event)
                                                   )
            await self.worker_queue.put(game_worker_task)

    async def start(self, update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send message on `/start`."""
        chat_id = update.message.chat.id
        ev = SearchPlayerEvent(chat_id=chat_id)

        task_put = asyncio.create_task(self.player_queue.put(ev))
        task_send = asyncio.create_task(
            update._bot.send_message(chat_id=chat_id,
                                     text='Wait player'))
        await asyncio.gather(task_send, task_put)

        task = asyncio.create_task(self.start_worker(update, context, ev))

        await self.worker_queue.put(task)

        return self.CONTINUE_GAME

    async def game_worker(self, message: Message,
                          context: ContextTypes.DEFAULT_TYPE,
                          event: MoveEvent):
        await event.wait()
        event.clear()

        fields = context.user_data['keyboard_state']
        room_hash = context.user_data['room_hash']
        x, y = event.turn_coord
        chat_id = message.chat.id

        async with self.rooms_lock:
            rooms_data = self.rooms[room_hash]

        opponent_symbol = rooms_data[rooms_data[chat_id]['opponent_chat_id']][
            'symbol']
        fields[y][x] = opponent_symbol

        context.user_data['keyboard_state'] = fields
        keyboard = self.generate_keyboard(fields)
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.edit_reply_markup(reply_markup=reply_markup)

        if self.tic_tac_toe.won(fields, rooms_data[chat_id]['symbol']):
            await asyncio.sleep(2)
            await message.edit_text('you won')

            return

        if self.tic_tac_toe.won(fields, opponent_symbol):
            await asyncio.sleep(2)
            await message.edit_text('you lose')

            return

        cells = self.tic_tac_toe.get_empty_cells(fields)
        if not cells:
            await asyncio.sleep(2)
            await message.edit_text('draw')

            return

    async def game(self, update: Update,
                   context: ContextTypes.DEFAULT_TYPE) -> int:
        """Main processing of the game"""

        fields = context.user_data['keyboard_state']
        y, x = map(int, update.callback_query.data)
        query = update.callback_query
        chat_id = query.message.chat.id
        room_hash = context.user_data['room_hash']

        keyboard = self.generate_keyboard(fields)
        reply_markup = InlineKeyboardMarkup(keyboard)

        async with self.rooms_lock:
            rooms_data = self.rooms[room_hash]

        if not rooms_data[chat_id]['turn']:
            await query.edit_message_text('not turn',
                                          reply_markup=reply_markup)
            return self.CONTINUE_GAME

        if fields[y][x] != self.tic_tac_toe.free_space:
            await query.edit_message_text('repeat', reply_markup=reply_markup)
            return self.CONTINUE_GAME

        fields[y][x] = rooms_data[chat_id]['symbol']

        context.user_data['keyboard_state'] = fields
        keyboard = self.generate_keyboard(fields)
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_reply_markup(reply_markup=reply_markup)

        move_event: MoveEvent = rooms_data['move_event']
        move_event.turn_coord = (x, y)
        move_event.set()

        return_state = self.CONTINUE_GAME
        if self.tic_tac_toe.won(fields, rooms_data[chat_id]['symbol']):
            await query.edit_message_text('you won')

            return_state = self.FINISH_GAME
        elif not self.tic_tac_toe.get_empty_cells(fields):
            await query.edit_message_text('draw')

            return_state = self.FINISH_GAME

        if return_state == self.CONTINUE_GAME:
            while move_event.is_set():
                await asyncio.sleep(1)

            game_worker_task = asyncio.create_task(
                self.game_worker(query.message,
                                 context,
                                 move_event))
            await self.worker_queue.put(game_worker_task)

            rooms_data[rooms_data[chat_id]['opponent_chat_id']]['turn'] = \
                rooms_data[chat_id]['turn']
            rooms_data[chat_id]['turn'] = not rooms_data[chat_id]['turn']
            async with self.rooms_lock:
                self.rooms[room_hash] = rooms_data
        else:
            async with self.rooms_lock:
                del self.rooms[room_hash]

        return return_state

    async def end(self, update: Update,
                  context: ContextTypes.DEFAULT_TYPE) -> int:
        """Returns `ConversationHandler.END`, which tells the
        ConversationHandler that the conversation is over.
        """
        # reset state to default, so you can play again with /start
        context.user_data[
            'keyboard_state'] = self.tic_tac_toe.get_default_state()
        del context.user_data['room_hash']

        query = update.callback_query

        await query.edit_message_text('game end')

        return ConversationHandler.END

    def set_handler(self):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                self.CONTINUE_GAME: [
                    CallbackQueryHandler(self.game,
                                         pattern='^' + f'{r}{c}' + '$')
                    for r in range(3)
                    for c in range(3)
                ],
                self.FINISH_GAME: [
                    CallbackQueryHandler(self.end,
                                         pattern='^' + f'{r}{c}' + '$')
                    for r in range(3)
                    for c in range(3)
                ],
            },
            fallbacks=[CommandHandler('start', self.start)],
        )

        self.application.add_handler(conv_handler)

    def run_application(self):
        self.set_handler()

        asyncio.set_event_loop(self.app_loop)

        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def search_player_daemon(self, player_queue: asyncio.Queue):
        while True:
            if player_queue.qsize() > 1:
                ev1: SearchPlayerEvent = await player_queue.get()
                ev2: SearchPlayerEvent = await player_queue.get()

                symbols = [self.tic_tac_toe.zero, self.tic_tac_toe.cross]
                if random.random() < 0.5:
                    symbols = [self.tic_tac_toe.cross, self.tic_tac_toe.zero]

                symbol1, symbol2 = symbols
                move_event = MoveEvent()
                h = await self.get_rooms_hash(ev1.chat_id, ev2.chat_id)

                async with self.rooms_lock:
                    self.rooms[h] = {
                        ev1.chat_id: {'opponent_chat_id': ev2.chat_id,
                                      'symbol': symbol1,
                                      'move_event': move_event,
                                      'turn': (symbol1 ==
                                               self.tic_tac_toe.cross)},
                        ev2.chat_id: {'opponent_chat_id': ev1.chat_id,
                                      'symbol': symbol2,
                                      'turn': (symbol2 ==
                                               self.tic_tac_toe.cross)},
                        'move_event': move_event,
                    }

                ev1.room_hash = h
                ev2.room_hash = h

                ev1.set()
                ev2.set()
            else:
                await asyncio.sleep(2)

    async def worker_daemon(self, worker_queue: asyncio.Queue):
        while True:
            worker = worker_queue.get()
            await worker

    async def run(self):
        app_coro = asyncio.to_thread(self.run_application)

        search_player_daemon_task = asyncio.create_task(
            self.search_player_daemon(self.player_queue))

        worker_daemon_task = asyncio.create_task(
            self.worker_daemon(self.worker_queue))

        await asyncio.gather(app_coro,
                             search_player_daemon_task,
                             worker_daemon_task)

    async def get_rooms_hash(self, h1: Hashable, h2: Hashable) -> int:
        c = 0
        h = hash((h1, h2, c))
        while True:
            async with self.rooms_lock:
                if h not in self.rooms:
                    break
            c += 1
            h = hash((h1, h2, c))

        return h


if __name__ == '__main__':
    app = App()
    asyncio.run(app.run())
