import math
from datetime import date, timedelta
from collections import defaultdict

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status, generics
from django.db.models import Q, Sum
from .models import (
    DiagnosisResult, Farm, Supplier, Expert, ChatRoom, ChatMessage,
    DailyTask, TaskCompletion, Article,
    VaccinationRecord, MortalityLog, TreatmentRecord,
)
from .serializers import (
    DiagnosisResultSerializer, DiagnosisResultDetailSerializer, UserProfileSerializer,
    SupplierSerializer, SupplierListSerializer, ExpertListSerializer, ExpertDetailSerializer,
    ChatRoomSerializer, ChatMessageSerializer,
    DailyTaskSerializer, ArticleListSerializer, ArticleDetailSerializer,
    VaccinationRecordSerializer, MortalityLogSerializer, TreatmentRecordSerializer,
)
from .ai_engine import predict_disease, predict_video, fetch_weather
from .notifications import send_fcm_notification
from firebase_admin import firestore as admin_firestore


class HealthView(APIView):
    """
    Public health check endpoint - no authentication required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})


class ProtectedView(APIView):
    """
    Protected endpoint - requires Firebase authentication.
    The user must include a valid Firebase ID token in the Authorization header.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'message': 'You are authenticated!',
            'user_id': request.user.id,
            'username': request.user.username,  # This is the Firebase UID
            'email': request.user.email,
            'display_name': request.user.first_name,
        })


class ProfileView(APIView):
    """
    GET /api/profile/: Returns user profile with farm details.
    PUT /api/profile/: Updates user and farm profile data in PostgreSQL.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get the user's first farm (or primary farm)
            farm = Farm.objects.filter(user=request.user).first()
            
            if not farm:
                return Response(
                    {'error': 'No farm assigned to this user'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = UserProfileSerializer(farm)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request):
        try:
            # Get the user's first farm (or primary farm)
            farm = Farm.objects.filter(user=request.user).first()
            
            if not farm:
                return Response(
                    {'error': 'No farm assigned to this user'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = UserProfileSerializer(farm, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PublicDataView(APIView):
    """
    Public endpoint that doesn't require authentication.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'message': 'This is public data accessible to everyone',
            'data': ['item1', 'item2', 'item3']
        })


class DiagnoseView(APIView):
    """
    POST endpoint to diagnose poultry disease from an uploaded image.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import logging, traceback
        logger = logging.getLogger(__name__)

        if 'image' not in request.FILES:
            return Response(
                {'error': 'No image provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        image_file = request.FILES['image']

        # Prefer weather values sent by the client when present — Flutter
        # fetches pressure_msl directly from Open-Meteo on the device, so
        # values stay accurate even if the Render worker has a stale
        # fetch_weather cache or the dyno is slow to update. Fall back to
        # the server-side fetch when any field is missing.
        lat = request.data.get('latitude')
        lon = request.data.get('longitude')

        def _num(val):
            try:
                return float(val) if val not in (None, '', 'null') else None
            except (TypeError, ValueError):
                return None

        client_weather = {
            'temperature': _num(request.data.get('temperature')),
            'humidity': _num(request.data.get('humidity')),
            'wind_speed': _num(request.data.get('wind_speed')),
            'pressure': _num(request.data.get('pressure')),
        }
        if all(v is not None for v in client_weather.values()):
            weather = client_weather
        else:
            weather = fetch_weather(lat, lon)
            for k, v in client_weather.items():
                if v is not None:
                    weather[k] = v

        try:
            prediction = predict_disease(image_file, weather=weather)
        except RuntimeError as exc:
            logger.warning('predict_disease RuntimeError: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            logger.error('predict_disease unexpected error:\n%s', traceback.format_exc())
            return Response({'error': f'Inference failed: {exc}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If the HF Space rejected the sample (not-feces or low confidence)
        # we return the payload *without* saving a DiagnosisResult — a
        # rejected photo is a UX signal, not a real diagnosis, and would
        # otherwise pollute the farmer's history as a false-positive alert.
        if prediction.get('rejected') is True:
            resp_data = {
                'rejected': True,
                'gate_failed': prediction.get('gate_failed'),
                'reason': prediction.get('reason'),
                'disease_name': prediction.get('disease_name', 'Rejected'),
                'confidence': prediction.get('confidence', 0.0),
                'all_probabilities': prediction.get('all_probabilities', {}),
                'image_stage_probabilities': prediction.get('image_stage_probabilities', {}),
                'image_stage_top_class': prediction.get('image_stage_top_class'),
                'image_stage_top_confidence': prediction.get('image_stage_top_confidence'),
                'yolo_detected': prediction.get('yolo_detected', False),
                'yolo_confidence': prediction.get('yolo_confidence', 0.0),
                'crop_preview_data_url': prediction.get('crop_preview_data_url'),
                'xai': prediction.get('xai'),
                'tips': prediction.get('tips', []),
                'pipeline': prediction.get('pipeline'),
                'weather': weather,
            }
            return Response(resp_data, status=status.HTTP_200_OK)

        try:
            is_healthy = prediction['disease_name'].lower() == 'healthy'
            farm = Farm.objects.filter(user=request.user).first()
            # ai_engine already rewinds, but be defensive — Django's storage
            # backend saves from the current cursor, and an EOF'd file would
            # persist empty bytes and later surface as "image cannot be opened".
            try:
                image_file.seek(0)
            except Exception:
                pass
            analysis_payload = {
                key: prediction[key]
                for key in (
                    'image_stage_probabilities',
                    'image_stage_top_class',
                    'image_stage_top_confidence',
                    'yolo_detected',
                    'yolo_confidence',
                    'crop_preview_data_url',
                    'xai',
                    'pipeline',
                    'accepted',
                    'rejected',
                    'weather',
                    'tips',
                )
                if key in prediction
            }
            if weather:
                analysis_payload['weather'] = weather

            diagnosis = DiagnosisResult.objects.create(
                user=request.user,
                farm=farm,
                image=image_file,
                disease_name=prediction['disease_name'],
                confidence=prediction['confidence'],
                all_probabilities=prediction.get('all_probabilities'),
                analysis_payload=analysis_payload or None,
                source='ai',
                status='Healthy' if is_healthy else 'Alert',
            )

            serializer = DiagnosisResultSerializer(diagnosis, context={'request': request})
            resp_data = serializer.data
            resp_data['tips'] = prediction.get('tips', [])
            resp_data['weather'] = weather
            # Pass through the rich metadata from the HF Space so the Flutter
            # client can render XAI overlays, YOLO crop previews, etc.
            for extra in (
                'image_stage_probabilities', 'image_stage_top_class',
                'image_stage_top_confidence', 'yolo_detected', 'yolo_confidence',
                'crop_preview_data_url', 'xai', 'pipeline', 'accepted', 'rejected',
            ):
                if extra in prediction:
                    resp_data[extra] = prediction[extra]
            return Response(resp_data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.error('DiagnoseView persistence failure:\n%s', traceback.format_exc())
            return Response(
                {'error': f'Failed to save diagnosis: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VideoDiagnoseView(APIView):
    """
    POST /api/diagnose-video/
    Accepts a multipart upload with field name 'video' plus optional
    lat/lon/weather, proxies the file to the HF Space /analyze-video
    endpoint, and returns the raw monitoring JSON (frame reports with
    detections, XAI heatmap data URLs, diagnosis counts, annotated video
    link). We do NOT persist video analyses into DiagnosisResult — they
    produce many detections, not a single clean row, so they're treated
    as an advisory monitoring tool for now.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import logging, traceback
        logger = logging.getLogger(__name__)

        if 'video' not in request.FILES:
            return Response(
                {'error': 'No video provided'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_file = request.FILES['video']
        # Match the mobile app guardrail. Large phone clips take too long to
        # upload through Render before inference even begins.
        if video_file.size and video_file.size > 20 * 1024 * 1024:
            return Response(
                {'error': 'Video exceeds 20 MB limit'},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        lat = request.data.get('latitude')
        lon = request.data.get('longitude')
        weather = fetch_weather(lat, lon)

        try:
            result = predict_video(video_file, weather=weather)
        except RuntimeError as exc:
            logger.warning('predict_video RuntimeError: %s', exc)
            return Response(
                {'error': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.error('predict_video unexpected error:\n%s', traceback.format_exc())
            return Response(
                {'error': f'Video inference failed: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Echo the farm + weather context alongside so the client can
        # render the farmer's own context on the result screen without a
        # second round-trip.
        farm = Farm.objects.filter(user=request.user).first()
        result['weather'] = weather
        if farm:
            result['farm_name'] = farm.name
        return Response(result, status=status.HTTP_200_OK)


class SaveVideoDiagnosisView(APIView):
    """
    POST /api/save-video-diagnosis/
    Accepts the JSON payload returned by the HF Space /analyze-video
    (Flutter calls HF directly to avoid Render's gunicorn timeout) and
    persists it as a DiagnosisResult row so the video monitoring run
    shows up in Reports/History alongside image diagnoses.

    Expected body fields (all optional except top_diagnosis):
      - top_diagnosis: str
      - confidence: float (0-100)
      - diagnosis_counts: {class: count}
      - weather: {temperature, humidity, wind_speed, pressure}
      - frame_reports: list (embedded in analysis_payload)
      - top_frame_data_url: data URL of the representative annotated
        frame — saved as the DiagnosisResult image so the Reports
        tile has something to show.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import base64
        import logging
        from django.core.files.base import ContentFile

        logger = logging.getLogger(__name__)
        data = request.data or {}

        disease_name = (data.get('top_diagnosis') or 'Unknown').strip()
        try:
            confidence = float(data.get('confidence') or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        is_healthy = disease_name.lower() == 'healthy'
        status_label = 'Healthy' if is_healthy else 'Alert'

        farm = Farm.objects.filter(user=request.user).first()

        diagnosis = DiagnosisResult(
            user=request.user,
            farm=farm,
            disease_name=disease_name,
            confidence=confidence,
            source='ai_video',
            status=status_label,
            all_probabilities=data.get('diagnosis_counts') or {},
            analysis_payload={
                'pipeline': 'video_monitoring',
                'weather': data.get('weather'),
                'frame_reports': data.get('frame_reports'),
                'diagnosis_counts': data.get('diagnosis_counts'),
                'processed_frames': data.get('processed_frames'),
                'source_duration_sec': data.get('source_duration_sec'),
                'xai_summary': data.get('xai_summary'),
                'tips': data.get('tips'),
            },
        )

        # Save the top representative frame as the row's image so the
        # Reports grid tile renders something meaningful instead of a
        # placeholder.
        top_url = data.get('top_frame_data_url')
        if isinstance(top_url, str) and top_url.startswith('data:image'):
            try:
                header, b64 = top_url.split(',', 1)
                ext = 'jpg'
                if 'image/png' in header:
                    ext = 'png'
                img_bytes = base64.b64decode(b64)
                diagnosis.image.save(
                    f'video_{request.user.id}_{int(confidence)}.{ext}',
                    ContentFile(img_bytes),
                    save=False,
                )
            except Exception as exc:
                logger.warning('video top-frame decode failed: %s', exc)

        try:
            diagnosis.save()
        except Exception as exc:
            logger.error('Failed to save video diagnosis: %s', exc)
            return Response(
                {'error': f'Failed to save: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                'id': diagnosis.id,
                'created_at': diagnosis.created_at.isoformat(),
                'disease_name': diagnosis.disease_name,
                'confidence': diagnosis.confidence,
                'source': diagnosis.source,
                'status': diagnosis.status,
            },
            status=status.HTTP_201_CREATED,
        )


class HistoryView(generics.ListCreateAPIView):
    """
    GET endpoint to retrieve all diagnosis results for the authenticated user.
    Results are sorted by newest first.
    Supports optional ?status= query param for filtering:
      - 'Healthy' → only healthy diagnoses
      - 'Alert'   → anything that is NOT healthy
      - omitted   → all diagnoses
    Requires authentication.
    """
    serializer_class = DiagnosisResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DiagnosisResult.objects.filter(user=self.request.user).order_by('-created_at')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter.lower() == 'alert':
                qs = qs.exclude(disease_name__iexact='healthy')
            else:
                qs = qs.filter(disease_name__iexact=status_filter)

        return qs

    def perform_create(self, serializer):
        farm = Farm.objects.filter(user=self.request.user).first()
        serializer.save(user=self.request.user, farm=farm)


class HistoryDetailView(generics.RetrieveDestroyAPIView):
    """
    DELETE endpoint to remove a single diagnosis record by its ID.
    Only the record owner can delete it.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return DiagnosisResultDetailSerializer
        return DiagnosisResultSerializer

    def get_queryset(self):
        return DiagnosisResult.objects.filter(user=self.request.user)


class FeedCalculatorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        flock_size = request.data.get('flock_size')
        bird_age_weeks = request.data.get('bird_age_weeks', 4)
        if not flock_size or int(flock_size) <= 0:
            return Response({'error': 'Valid flock_size required'}, status=status.HTTP_400_BAD_REQUEST)

        flock_size = int(flock_size)
        bird_age_weeks = int(bird_age_weeks)

        # Feed: ~120g per bird per day for adult, scale by age
        feed_per_bird_g = min(120, 30 + bird_age_weeks * 10)
        daily_feed_kg = (flock_size * feed_per_bird_g) / 1000
        bags_per_month = math.ceil((daily_feed_kg * 30) / 50)  # 50kg bags

        # Water: ~250ml per bird per day
        daily_water_liters = (flock_size * 250) / 1000

        # Vaccination cost estimate
        vaccine_per_bird = 5  # PKR
        monthly_vaccine_cost = flock_size * vaccine_per_bird

        return Response({
            'flock_size': flock_size,
            'bird_age_weeks': bird_age_weeks,
            'daily_feed_kg': round(daily_feed_kg, 1),
            'bags_per_month': bags_per_month,
            'daily_water_liters': round(daily_water_liters, 1),
            'monthly_vaccine_cost': monthly_vaccine_cost,
            'feed_per_bird_g': feed_per_bird_g,
        })


class SupplierListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplierListSerializer

    def get_queryset(self):
        qs = Supplier.objects.filter(is_active=True)
        supplier_type = self.request.query_params.get('type')
        if supplier_type:
            qs = qs.filter(supplier_type=supplier_type)
        return qs


class SupplierDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.filter(is_active=True)


class ExpertListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpertListSerializer
    queryset = Expert.objects.filter(is_available=True)


class ExpertDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpertDetailSerializer
    queryset = Expert.objects.all()


class ChatRoomListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rooms = ChatRoom.objects.filter(Q(farmer=request.user) | Q(expert=request.user))
        serializer = ChatRoomSerializer(rooms, many=True)
        return Response(serializer.data)

    def post(self, request):
        expert_id = request.data.get('expert_id')
        if not expert_id:
            return Response({'error': 'expert_id required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            expert = Expert.objects.get(id=expert_id)
        except Expert.DoesNotExist:
            return Response({'error': 'Expert not found'}, status=status.HTTP_404_NOT_FOUND)

        room, created = ChatRoom.objects.get_or_create(
            farmer=request.user, expert=expert.user
        )
        serializer = ChatRoomSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ChatMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_room_for_user(self, room_id, user):
        return ChatRoom.objects.filter(id=room_id).filter(Q(farmer=user) | Q(expert=user)).first()

    def get(self, request, room_id):
        room = self._get_room_for_user(room_id, request.user)
        if room is None:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

        # Mark messages from expert as read
        room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

        messages = room.messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, room_id):
        room = self._get_room_for_user(room_id, request.user)
        if room is None:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

        message_text = request.data.get('message')
        if not message_text:
            return Response({'error': 'message required'}, status=status.HTTP_400_BAD_REQUEST)

        msg = ChatMessage.objects.create(room=room, sender=request.user, message=message_text)
        room.save()  # update updated_at

        # Send FCM push notification to the recipient
        recipient = room.expert if request.user == room.farmer else room.farmer
        recipient_farm = Farm.objects.filter(user=recipient).first()
        if recipient_farm and recipient_farm.fcm_token:
            sender_name = request.user.first_name or 'Someone'
            send_fcm_notification(
                fcm_token=recipient_farm.fcm_token,
                title=f'New message from {sender_name}',
                body=message_text[:100],
                data={'type': 'chat', 'room_id': str(room.id), 'sender_name': sender_name},
            )

        # Write to Firestore for real-time Flutter stream
        try:
            db = admin_firestore.client()
            db.collection('chats').document(str(room_id)).collection('messages').document(str(msg.id)).set({
                'id': msg.id,
                'message': msg.message,
                'sender_name': request.user.first_name or request.user.username or 'User',
                'is_farmer': (request.user == room.farmer),
                'created_at': msg.created_at,
            })
        except Exception:
            pass  # Firestore write failure must not break the API

        serializer = ChatMessageSerializer(msg)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        farm = Farm.objects.filter(user=request.user).first()
        flock_size = farm.flock_size if farm else 0

        tasks = DailyTask.objects.filter(is_active=True, min_flock_size__lte=flock_size)

        # Filter by season
        current_month = today.month
        if current_month in [6, 7, 8]:
            season = 'summer'
        elif current_month in [12, 1, 2]:
            season = 'winter'
        else:
            season = 'spring'
        tasks = tasks.filter(season__in=[season, 'all'])

        serializer = DailyTaskSerializer(tasks, many=True, context={'request': request, 'date': today})
        return Response(serializer.data)


class TaskCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        today = date.today()
        try:
            task = DailyTask.objects.get(id=task_id)
        except DailyTask.DoesNotExist:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        completion, created = TaskCompletion.objects.get_or_create(
            user=request.user, task=task, date=today
        )
        if not created:
            return Response({'message': 'Already completed'})
        return Response({'message': 'Task completed'}, status=status.HTTP_201_CREATED)

    def delete(self, request, task_id):
        today = date.today()
        deleted, _ = TaskCompletion.objects.filter(
            user=request.user, task_id=task_id, date=today
        ).delete()
        if deleted:
            return Response({'message': 'Task uncompleted'})
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class TaskSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        farm = Farm.objects.filter(user=request.user).first()
        flock_size = farm.flock_size if farm else 0

        eligible_tasks = DailyTask.objects.filter(
            is_active=True,
            min_flock_size__lte=flock_size,
        )
        total = eligible_tasks.count()
        completed = TaskCompletion.objects.filter(
            user=request.user,
            date=today,
            task__in=eligible_tasks,
        ).count()
        pending = max(total - completed, 0)

        return Response({
            'total': total,
            'completed': completed,
            'pending': pending,
        })


class ArticleListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleListSerializer

    def get_queryset(self):
        qs = Article.objects.filter(is_published=True)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs


class ArticleDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleDetailSerializer
    queryset = Article.objects.filter(is_published=True)


# ---------------------------------------------------------------------------
# Flock Health Records
# ---------------------------------------------------------------------------

class VaccinationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = VaccinationRecord.objects.filter(farm=farm)
        return Response(VaccinationRecordSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VaccinationRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VaccinationDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VaccinationRecordSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return VaccinationRecord.objects.none()
        return VaccinationRecord.objects.filter(farm=farm)


class MortalityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = MortalityLog.objects.filter(farm=farm)
        return Response(MortalityLogSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MortalityLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MortalityDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MortalityLogSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return MortalityLog.objects.none()
        return MortalityLog.objects.filter(farm=farm)


class TreatmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response([])
        records = TreatmentRecord.objects.filter(farm=farm)
        return Response(TreatmentRecordSerializer(records, many=True).data)

    def post(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TreatmentRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(farm=farm)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TreatmentDetailView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TreatmentRecordSerializer

    def get_queryset(self):
        farm = Farm.objects.filter(user=self.request.user).first()
        if not farm:
            return TreatmentRecord.objects.none()
        return TreatmentRecord.objects.filter(farm=farm)


class FlockSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = Farm.objects.filter(user=request.user).first()
        if not farm:
            return Response({'error': 'No farm found'}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        total_mortality = MortalityLog.objects.filter(
            farm=farm, date__gte=thirty_days_ago
        ).aggregate(total=Sum('count'))['total'] or 0

        upcoming_vaccinations = VaccinationRecord.objects.filter(
            farm=farm,
            next_due_date__gte=today,
            next_due_date__lte=today + timedelta(days=30),
        ).values('vaccine_name', 'next_due_date').order_by('next_due_date')[:5]

        active_treatments = TreatmentRecord.objects.filter(
            farm=farm,
            start_date__lte=today,
        ).filter(end_date__isnull=True) | TreatmentRecord.objects.filter(
            farm=farm,
            start_date__lte=today,
            end_date__gte=today,
        )

        return Response({
            'mortality_last_30_days': total_mortality,
            'upcoming_vaccinations': list(upcoming_vaccinations),
            'active_treatments': TreatmentRecordSerializer(active_treatments.distinct(), many=True).data,
        })


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)
        farm = Farm.objects.filter(user=request.user).first()

        # Diagnosis trend: count per day for last 30 days
        diagnoses = DiagnosisResult.objects.filter(
            user=request.user, created_at__date__gte=thirty_days_ago
        ).values('created_at__date', 'status')

        trend_map = defaultdict(lambda: {'count': 0, 'alerts': 0})
        for d in diagnoses:
            day = str(d['created_at__date'])
            trend_map[day]['count'] += 1
            if d['status'] == 'Alert':
                trend_map[day]['alerts'] += 1
        diagnosis_trend = [
            {'date': k, 'count': v['count'], 'alerts': v['alerts']}
            for k, v in sorted(trend_map.items())
        ]

        # Disease breakdown
        disease_counts = defaultdict(int)
        for d in DiagnosisResult.objects.filter(user=request.user):
            disease_counts[d.disease_name] += 1
        disease_breakdown = [
            {'disease': k, 'count': v}
            for k, v in sorted(disease_counts.items(), key=lambda x: -x[1])
        ]

        # Task completion rate (last 7 days)
        flock_size = farm.flock_size if farm else 0
        eligible_tasks = DailyTask.objects.filter(is_active=True, min_flock_size__lte=flock_size)
        total_possible = eligible_tasks.count() * 7
        completed_count = TaskCompletion.objects.filter(
            user=request.user,
            date__gte=today - timedelta(days=7),
            task__in=eligible_tasks,
        ).count()
        task_completion_rate = round(completed_count / total_possible, 2) if total_possible > 0 else 0.0

        # Mortality trend (last 30 days)
        mortality_data = []
        if farm:
            mort_qs = MortalityLog.objects.filter(farm=farm, date__gte=thirty_days_ago).values('date', 'count')
            mort_map = {str(m['date']): m['count'] for m in mort_qs}
            mortality_data = [
                {'date': str(thirty_days_ago + timedelta(days=i)),
                 'count': mort_map.get(str(thirty_days_ago + timedelta(days=i)), 0)}
                for i in range(31)
            ]

        # Upcoming vaccinations
        upcoming_vaccinations = []
        if farm:
            upcoming_vaccinations = list(
                VaccinationRecord.objects.filter(
                    farm=farm,
                    next_due_date__gte=today,
                    next_due_date__lte=today + timedelta(days=30),
                ).values('vaccine_name', 'next_due_date').order_by('next_due_date')[:5]
            )
            for v in upcoming_vaccinations:
                v['next_due_date'] = str(v['next_due_date'])

        # Flock health score (0-100)
        alert_count = DiagnosisResult.objects.filter(
            user=request.user, status='Alert', created_at__date__gte=thirty_days_ago
        ).count()
        total_mortality_score = MortalityLog.objects.filter(
            farm=farm, date__gte=thirty_days_ago
        ).aggregate(total=Sum('count'))['total'] or 0 if farm else 0
        missed_tasks = max(0, (eligible_tasks.count() * 7) - completed_count)
        deductions = min(40, alert_count * 5) + min(30, total_mortality_score * 2) + min(20, missed_tasks)
        flock_health_score = max(0, 100 - deductions)

        return Response({
            'diagnosis_trend': diagnosis_trend,
            'disease_breakdown': disease_breakdown,
            'task_completion_rate': task_completion_rate,
            'mortality_trend': mortality_data,
            'vaccination_upcoming': upcoming_vaccinations,
            'flock_health_score': flock_health_score,
        })


# ─────────────────────────────────────────────────────────────────────────────
#  Market Rates (Daily Egg Peti / Broiler / Feed)
# ─────────────────────────────────────────────────────────────────────────────

class MarketRatesView(APIView):
    """GET /api/market-rates/ → latest rate for every region.

    Reads from Firestore `market_rates_latest/*`. Falls back to returning an
    empty list if Firestore is unavailable (the app should use its cached
    Firestore snapshot).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            from firebase_admin import firestore as admin_firestore
            from django.conf import settings
            if not getattr(settings, 'FIREBASE_INITIALIZED', False):
                return Response({'rates': [], 'source': 'unavailable'})
            db = admin_firestore.client()
            docs = db.collection('market_rates_latest').stream()
            payload = []
            for d in docs:
                item = d.to_dict()
                # updated_at is a Firestore timestamp; stringify for JSON.
                if 'updated_at' in item and hasattr(item['updated_at'], 'isoformat'):
                    item['updated_at'] = item['updated_at'].isoformat()
                payload.append(item)
            payload.sort(key=lambda x: x.get('region_key', ''))
            return Response({'rates': payload, 'source': 'firestore'})
        except Exception as e:
            return Response({'rates': [], 'source': 'error', 'detail': str(e)}, status=200)


class MarketRatesRegionView(APIView):
    """GET /api/market-rates/<region_key>/ → today + 30-day history for a region."""
    permission_classes = [AllowAny]

    def get(self, request, region_key: str):
        try:
            from firebase_admin import firestore as admin_firestore
            from django.conf import settings
            if not getattr(settings, 'FIREBASE_INITIALIZED', False):
                return Response({'history': []})
            db = admin_firestore.client()
            q = (
                db.collection('market_rates')
                .where('region_key', '==', region_key)
                .order_by('date', direction=admin_firestore.Query.DESCENDING)
                .limit(30)
            )
            rows = []
            for d in q.stream():
                item = d.to_dict()
                if 'updated_at' in item and hasattr(item['updated_at'], 'isoformat'):
                    item['updated_at'] = item['updated_at'].isoformat()
                rows.append(item)
            return Response({'region_key': region_key, 'history': rows})
        except Exception as e:
            return Response({'history': [], 'detail': str(e)}, status=200)
