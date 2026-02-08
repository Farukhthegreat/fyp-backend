from rest_framework import authentication, exceptions
from firebase_admin import auth
from django.contrib.auth.models import User
from .models import Farm


class FirebaseAuthentication(authentication.BaseAuthentication):
    """
    Custom DRF authentication class that validates Firebase ID tokens
    and implements Just-in-Time (JIT) Provisioning.

    Expected header format:
    Authorization: Bearer <firebase_id_token>

    JIT Provisioning Flow:
    1. Verifies the Firebase ID token
    2. Extracts uid, email, and display_name from the token
    3. Tries to get the Django User by username=uid
    4. If User doesn't exist:
       - Auto-creates User with username=uid
       - Auto-creates a default Farm for the user
    5. If User exists but has no Farm:
       - Auto-creates a default Farm for the user
    6. Returns (user, None) to proceed with the request

    This allows any valid Firebase user (Google, Phone, Email) to access
    the API immediately without manual database entry.
    """

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header:
            return None

        if not auth_header.startswith('Bearer '):
            return None

        id_token = auth_header.split('Bearer ')[1]

        try:
            # Verify the Firebase ID token
            decoded_token = auth.verify_id_token(id_token)

            uid = decoded_token.get('uid')
            email = decoded_token.get('email', '')
            phone_number = decoded_token.get('phone_number', '')
            display_name = decoded_token.get('name', '')

            # JIT Provisioning: Try to get existing user
            try:
                user = User.objects.get(username=uid)
                
                # Update user info if changed
                updated = False
                if email and user.email != email:
                    user.email = email
                    updated = True
                if display_name and user.first_name != display_name[:30]:
                    user.first_name = display_name[:30]
                    updated = True
                if updated:
                    user.save()

            except User.DoesNotExist:
                # Auto-create User if it doesn't exist
                user = User.objects.create_user(
                    username=uid,
                    email=email,
                    first_name=display_name[:30] if display_name else '',
                    password=None  # Firebase handles authentication
                )
                
                # Set phone number as last_name if no display_name (for phone auth)
                if not display_name and phone_number:
                    user.last_name = phone_number[:30]
                    user.save()

            # Ensure user has a Farm - create one if missing
            if not Farm.objects.filter(user=user).exists():
                Farm.objects.create(
                    user=user,
                    name="My Farm",
                    location="Not specified",
                    flock_size=0
                )

            # Return the Django User object
            return (user, None)

        except auth.InvalidIdTokenError:
            raise exceptions.AuthenticationFailed('Invalid Firebase ID token')
        except auth.ExpiredIdTokenError:
            raise exceptions.AuthenticationFailed('Expired Firebase ID token')
        except Exception as e:
            raise exceptions.AuthenticationFailed(f'Authentication failed: {str(e)}')

    def authenticate_header(self, request):
        return 'Bearer'

