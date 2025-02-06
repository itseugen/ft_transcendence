from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Game, Tournement
import json
from asgiref.sync import sync_to_async
from .pong import PongGame
import asyncio
from django.utils import timezone
import sys

games = {}


class GameConsumer(AsyncWebsocketConsumer):
	async def connect(self):
		self.game_id = self.scope['url_route']['kwargs']['game_id']
		self.room_group_name = f'game_{self.game_id}'

		# Stelle sicher, dass ein zentrales Spiel verwendet wird
		if self.game_id not in games:
			games[self.game_id] = PongGame('player1', 'player2')
		self.game = games[self.game_id]

		# Gruppe hinzufügen
		await self.channel_layer.group_add(self.room_group_name, self.channel_name)
		await self.accept()

	async def disconnect(self, close_code):
		await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

	async def receive(self, text_data):
		text_data_json = json.loads(text_data)
		use = text_data_json['use']

		if use == 'ready_button':
			user = text_data_json['user']
			game_id = text_data_json['game_id']
			await self.save_message(user, game_id)
			await self.channel_layer.group_send(
				self.room_group_name,
				{
					'type': 'readyButton',
					'use': use,
					'user': user,
				},
			)

		if use == 'KeyboardEvent':
			user = text_data_json['user']
			game_id = text_data_json['game_id']
			key = text_data_json['key']
			await self.KeyboardInterrupt(user, game_id, key)

	async def KeyboardInterrupt(self, user, game_id, key):
		game = await sync_to_async(Game.objects.get)(id=game_id)
		user1_control = game.player1_control_settings
		user2_control = game.player2_control_settings
		user1 = await sync_to_async(lambda: game.player1.profile.user.username)()
		user2 = await sync_to_async(lambda: game.player2.profile.user.username)()

		if user1 == user:
			if user1_control == 'w_s':
				if key == 'KeyDownW':
					key = 'KeyDownArrowUp'
				elif key == 'KeyDownS':
					key = 'KeyDownArrowDown'
				elif key == 'KeyUpW':
					key = 'KeyUpArrowUp'
				elif key == 'KeyUpS':
					key = 'KeyUpArrowDown'
			self.game.move_paddle('player1', key)
		elif user2 == user:
			if user2_control == 'w_s':
				if key == 'KeyDownW':
					key = 'KeyDownArrowUp'
				elif key == 'KeyDownS':
					key = 'KeyDownArrowDown'
				elif key == 'KeyUpW':
					key = 'KeyUpArrowUp'
				elif key == 'KeyUpS':
					key = 'KeyUpArrowDown'
			self.game.move_paddle('player2', key)

	async def readyButton(self, event):
		use = event['use']
		user = event['user']
		await self.send(
			text_data=json.dumps(
				{
					'use': use,
					'user': user,
				}
			)
		)

	async def save_message(self, user, game_id):
		game = await sync_to_async(Game.objects.get)(id=game_id)
		# Use sync_to_async to access related fields in an async context
		user1 = await sync_to_async(lambda: game.player1.profile.user.username)()
		user2 = await sync_to_async(lambda: game.player2.profile.user.username)()

		if not (game.player1_ready and game.player2_ready):
			if user1 == user:
				game.player1_ready = True
			if user2 == user:
				game.player2_ready = True
			if game.player1_ready and game.player2_ready:
				asyncio.create_task(self.start_game_loop())
			await sync_to_async(game.save)()

	async def start_game_loop(self):
		async def broadcast_callback(state):
			# If there is a winner played at time gets set to the end time of the game
			json_state = json.loads(state)
			winner = json_state['winner']
			if winner['player1'] or winner['player2']:
				game = await sync_to_async(Game.objects.get)(id=self.game_id)
				game.pending = False
				game.played_at = timezone.now()
				player1 = await sync_to_async(lambda: game.player1)()
				player2 = await sync_to_async(lambda: game.player2)()

				profile1 = await sync_to_async(lambda: player1.profile)()
				profile2 = await sync_to_async(lambda: player2.profile)()

				if winner['player1']:
					player1.matches_won += 1
					player2.matches_lost += 1
					profile1.pong_games_won += 1
					profile2.pong_games_lost += 1
				if winner['player2']:
					player2.matches_won += 1
					player1.matches_lost += 1
					profile2.pong_games_won += 1
					profile1.pong_games_lost += 1

				await sync_to_async(profile1.save)()
				await sync_to_async(profile2.save)()
				await sync_to_async(player1.save)()
				await sync_to_async(player2.save)()
				await sync_to_async(game.save)()
			###

			await self.channel_layer.group_send(
				self.room_group_name,
				{
					'type': 'game_state',
					'state': state,
				},
			)

		# start the gameloop
		await self.game.game_loop(broadcast_callback)

	# send Gamestats to clients
	async def game_state(self, event):
		state = event['state']
		await self.send(
			text_data=json.dumps(
				{
					'use': 'game_state',
					'state': json.loads(state),
				}
			)
		)


# New Socket connection for creating games
class BasePageConsumer(AsyncWebsocketConsumer):
	async def connect(self):
		self.group_name = 'base_page_group'

		await self.channel_layer.group_add(self.group_name, self.channel_name)
		await self.accept()

	async def disconnect(self, close_code):
		await self.channel_layer.group_discard(self.group_name, self.channel_name)

	async def receive(self, text_data):
		data = json.loads(text_data)
		use = data['message']

		if use == 'create_game':
			await self.send_game_created(data['player1'], data['player2'], data['game_id'])
		if use == 'create_tournement':
			await self.send_tournement_created(data['host'], data['tournement_id'])

	async def send_game_created(self, player1, player2, game_id):
		response = {
			'message': 'game_created',
			'player1': player1,
			'player2': player2,
			'game_id': game_id,
		}
		await self.channel_layer.group_send(
			self.group_name, {'type': 'game_created', 'message': response}
		)

	async def send_tournement_created(self, host, tournement_id):
		sys.stdout.flush()
		response = {'message': 'create_tournement', 'host': host, 'tournement_id': tournement_id}
		await self.channel_layer.group_send(
			self.group_name, {'type': 'create_tournement', 'message': response}
		)

	async def create_tournement(self, event):
		await self.send(text_data=json.dumps(event['message']))

	async def game_created(self, event):
		await self.send(text_data=json.dumps(event['message']))


class TournementConsumer(AsyncWebsocketConsumer):
	async def connect(self):
		self.tournement_id = self.scope['url_route']['kwargs']['tournement_id']
		self.group_name = f'tournement_{self.tournement_id}'
		self.tournement = await sync_to_async(Tournement.objects.get)(id=self.tournement_id)
		self.group_name = f'tournement_{self.tournement_id}'
		self.user = self.scope.get('user').username

		# check if user is already in the tournement
		if self.user not in [
			self.tournement.host,
			self.tournement.player1,
			self.tournement.player2,
			self.tournement.player3,
		]:
			await self.add_user_to_tournement(self.user)

		await self.channel_layer.group_add(self.group_name, self.channel_name)
		await self.accept()

		print(f'WebSocket connected: {self.tournement_id}')

	async def disconnect(self, close_code):
		await self.channel_layer.group_discard(self.group_name, self.channel_name)
		print(f'WebSocket disconnected: {self.tournement_id}')

	async def add_user_to_tournement(self, username):
		def update_tournement():
			updated_field = None
			if not self.tournement.player1:
				self.tournement.player1 = username
				updated_field = 'player1'
			elif not self.tournement.player2:
				self.tournement.player2 = username
				updated_field = 'player2'
			elif not self.tournement.player3:
				self.tournement.player3 = username
				updated_field = 'player3'
			self.tournement.playernum += 1
			self.tournement.save()
			return updated_field, self.tournement.playernum

		updated_field, updated_playernum = await sync_to_async(update_tournement)()

		if updated_field:
			await self.channel_layer.group_send(
				self.group_name,
				{
					'type': 'player_joined',
					'username': username,
					'field': updated_field,
					'playerNum': updated_playernum,
				},
			)

	async def player_joined(self, event):
		print('Event received in player_joined:', event)
		sys.stdout.flush()
		await self.send(
			text_data=json.dumps(
				{
					'use': 'join',
					'username': event['username'],
					'field': event['field'],
					'playerNum': event['playerNum'],
				}
			)
		)

	async def receive(self, text_data):
		data = json.loads(text_data)
		action = data.get('use')

		if action == 'sync':
			tournement_data = {
				'use': 'sync',
				'host': self.tournement.host,
				'player1': self.tournement.player1,
				'player2': self.tournement.player2,
				'player3': self.tournement.player3,
				'playerNum': self.tournement.playernum,
			}
			await self.send(text_data=json.dumps(tournement_data))

		elif action == 'createGames':
			response_data = {
				'use': 'createGames',
				'status': 'success',
				'message': 'Games created successfully',
				'data': data,
			}

			await self.channel_layer.group_send(
				self.group_name, {'type': 'broadcast_create_games', 'response': response_data}
			)
			print('\n\n\nCreated Games and sent to all clients\n\n\n')
			sys.stdout.flush()

	async def broadcast_create_games(self, event):
		await self.send(text_data=json.dumps(event['response']))
