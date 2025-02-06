from .models import PongGame, Tournement
import sys

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from rest_framework import status


User = get_user_model()


# API for game creation
class CreateGameView(APIView):
	# For testing CLI comment permission_classes cause canot acces csrf_token
	permission_classes = [IsAuthenticated]

	print('\nAPI CreateGameView\n')
	sys.stdout.flush()

	def post(self, request):
		opponent_username = request.data.get('opponent')
		user_username = request.data.get('username')
		if not opponent_username:
			return Response(
				{'error': 'Opponent username is required.'}, status=status.HTTP_400_BAD_REQUEST
			)

		if opponent_username == request.user.username:
			return Response(
				{'error': 'You cannot play against yourself.'}, status=status.HTTP_400_BAD_REQUEST
			)

		try:
			opponent = User.objects.get(username=opponent_username)
		except User.DoesNotExist:
			return Response({'error': 'Opponent does not exist.'}, status=status.HTTP_404_NOT_FOUND)

		try:
			player = User.objects.get(username=user_username)
		except User.DoesNotExist:
			return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

		# @audit not used
		request.data.get('tournement', 0)

		# Create the game
		game = PongGame.objects.create(player1=player, player2=opponent)
		game.save()

		return Response(
			{'game_id': game.id, 'message': 'Game created successfully.'},
			status=status.HTTP_201_CREATED,
		)


class ScoreBoardView(APIView):
	# For testing CLI comment permission_classes cause canot acces csrf_token
	# permission_classes = [IsAuthenticated]

	def post(self, request):
		game_id = request.data.get('game_id')
		score1 = request.data.get('score1')
		score2 = request.data.get('score2')

		if not game_id:
			return Response(
				{'error': 'game_id score1 and score2 are required'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		try:
			game = PongGame.objects.get(id=game_id)
		except PongGame.DoesNotExist:
			return Response({'error': 'Game not found.'}, status=status.HTTP_404_NOT_FOUND)

		game.score1 = int(score1)
		game.score2 = int(score2)
		game.save()

		return Response({'scores': 'Game successfully saved score.'}, status=status.HTTP_200_OK)


class ControllKeySetting(APIView):
	# permission_classes = [IsAuthenticated]

	def post(self, request):
		game_id = request.data.get('game_id')
		username = request.data.get('username')

		if username:
			user = User.objects.filter(username=username)
		else:
			user = User.objects.filter(username=request.user.username)

		control1 = request.data.get('control1')
		control2 = request.data.get('control2')

		if not game_id or control1 is None or control2 is None:
			return Response(
				{'error': 'game_id, control1, and control2 are required.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		try:
			game = PongGame.objects.get(id=game_id)
		except PongGame.DoesNotExist:
			return Response({'error': 'Game not found.'}, status=status.HTTP_404_NOT_FOUND)

		if user == game.player1:
			game.player1_control_settings = control1
		elif user == game.player2:
			game.player2_control_settings = control2
		else:
			return Response(
				{'error': 'You are not a player in this game.'}, status=status.HTTP_403_FORBIDDEN
			)

		game.save()

		return Response(
			{'message': f'Control settings successfully updated for user {user}.'},
			status=status.HTTP_200_OK,
		)


class CreateTournement(APIView):
	# permission_classes = [IsAuthenticated]

	def post(self, request):
		username = request.data.get('username')

		try:
			User.objects.get(username=username)
		except User.DoesNotExist:
			return Response({'error': 'user does not exist.'}, status=status.HTTP_404_NOT_FOUND)

		tournement = Tournement.objects.create(host=username)
		tournement.save()
		return Response(
			{'tournement_id': tournement.id, 'message': 'Tournement created successfully.'},
			status=status.HTTP_201_CREATED,
		)
