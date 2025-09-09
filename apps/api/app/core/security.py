"""
Módulo de seguridad y autenticación para Axonote.
Incluye JWT, hashing de passwords y middleware de seguridad.
"""

from datetime import datetime, timedelta
from typing import Any, Optional, Union

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import settings


# Contexto para hashing de passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    """Datos del token JWT."""
    sub: Optional[str] = None
    exp: Optional[datetime] = None


def create_access_token(
    subject: Union[str, Any], 
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Crear token JWT de acceso.
    
    Args:
        subject: Sujeto del token (user_id, etc.)
        expires_delta: Tiempo de expiración personalizado
    
    Returns:
        Token JWT string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm="HS256"
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verificar y decodificar token JWT.
    
    Args:
        token: Token JWT a verificar
    
    Returns:
        TokenData si es válido, None si no
    """
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=["HS256"]
        )
        user_id: str = payload.get("sub")
        exp: datetime = payload.get("exp")
        
        if user_id is None:
            return None
            
        return TokenData(sub=user_id, exp=exp)
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verificar password contra hash.
    
    Args:
        plain_password: Password en texto plano
        hashed_password: Password hasheado
    
    Returns:
        True si coincide, False si no
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hashear password.
    
    Args:
        password: Password en texto plano
    
    Returns:
        Password hasheado
    """
    return pwd_context.hash(password)


def generate_api_key() -> str:
    """
    Generar API key segura.
    
    Returns:
        API key string
    """
    import secrets
    return f"axnote_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(32))}"


class SecurityHeaders:
    """Headers de seguridad estándar."""
    
    @staticmethod
    def get_security_headers() -> dict:
        """Obtener headers de seguridad recomendados."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": (
                "accelerometer=(), "
                "camera=(), "
                "geolocation=(), "
                "gyroscope=(), "
                "magnetometer=(), "
                "microphone=(self), "
                "payment=(), "
                "usb=()"
            )
        }


def validate_upload_file(
    filename: str, 
    content_type: str, 
    file_size: int,
    allowed_extensions: list
) -> tuple[bool, str]:
    """
    Validar archivo subido.
    
    Args:
        filename: Nombre del archivo
        content_type: Tipo MIME
        file_size: Tamaño en bytes
        allowed_extensions: Extensiones permitidas
    
    Returns:
        (es_válido, mensaje_error)
    """
    # Validar extensión
    if not filename:
        return False, "Nombre de archivo requerido"
    
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    if extension not in allowed_extensions:
        return False, f"Extensión no permitida. Permitidas: {', '.join(allowed_extensions)}"
    
    # Validar tamaño
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"Archivo demasiado grande. Máximo: {settings.MAX_UPLOAD_SIZE_MB}MB"
    
    # Validar tipo MIME básico
    audio_mimes = [
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/mpeg", "audio/mp3",
        "audio/mp4", "audio/m4a",
        "audio/flac", "audio/x-flac",
        "audio/ogg", "audio/vorbis"
    ]
    
    image_mimes = [
        "image/jpeg", "image/jpg",
        "image/png",
        "image/webp"
    ]
    
    if extension in settings.ALLOWED_AUDIO_FORMATS and content_type not in audio_mimes:
        return False, f"Tipo MIME no válido para audio: {content_type}"
    
    if extension in settings.ALLOWED_IMAGE_FORMATS and content_type not in image_mimes:
        return False, f"Tipo MIME no válido para imagen: {content_type}"
    
    return True, "Archivo válido"


def sanitize_filename(filename: str) -> str:
    """
    Sanitizar nombre de archivo.
    
    Args:
        filename: Nombre original
    
    Returns:
        Nombre sanitizado
    """
    import re
    import unicodedata
    
    # Normalizar unicode
    filename = unicodedata.normalize('NFKD', filename)
    
    # Remover caracteres no ASCII
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    
    # Remover caracteres peligrosos
    filename = re.sub(r'[^\w\s.-]', '', filename)
    
    # Limitar longitud
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]
    
    return filename.strip()
