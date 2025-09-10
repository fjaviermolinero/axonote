"""
Servicio de autenticación avanzado para Axonote.
Incluye JWT con refresh tokens, MFA, y auditoría completa.
"""

import secrets
import uuid
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.core.config import settings
from app.models.usuario import (
    Usuario, SesionUsuario, LogAuditoria, RolUsuario, EstadoUsuario,
    TipoEventoAuditoria, NivelSeveridad, PermisosUsuario
)
from app.services.encryption_service import ServicioCifrado


class ServicioAutenticacion:
    """Servicio completo de autenticación y autorización."""
    
    def __init__(self, db: Session, servicio_cifrado: Optional[ServicioCifrado] = None):
        self.db = db
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.algoritmo = "HS256"
        self.cifrado = servicio_cifrado or ServicioCifrado(settings.SECRET_KEY)
        
    async def registrar_usuario(
        self,
        email: str,
        password: str,
        nombre_completo: str,
        rol: RolUsuario = RolUsuario.ESTUDIANTE,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Usuario:
        """Registra un nuevo usuario con validaciones de seguridad."""
        
        # Validar fortaleza de contraseña
        if not self._validar_password_seguro(password):
            await self._log_evento_auditoria(
                TipoEventoAuditoria.USUARIO_CREADO,
                "Intento de registro con contraseña débil",
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="fallido",
                severidad=NivelSeveridad.WARNING,
                datos_evento={"email": email, "razon": "contraseña_debil"}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "La contraseña no cumple los requisitos de seguridad",
                    "requirements": {
                        "min_length": 12,
                        "requires_uppercase": True,
                        "requires_lowercase": True,
                        "requires_number": True,
                        "requires_special": True
                    }
                }
            )
        
        # Verificar si el usuario ya existe
        usuario_existente = self.db.query(Usuario).filter(Usuario.email == email).first()
        if usuario_existente:
            await self._log_evento_auditoria(
                TipoEventoAuditoria.USUARIO_CREADO,
                "Intento de registro con email existente",
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="fallido",
                severidad=NivelSeveridad.WARNING,
                datos_evento={"email": email}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está registrado"
            )
        
        # Crear usuario
        password_hash = self.pwd_context.hash(password)
        token_verificacion = secrets.token_urlsafe(32)
        
        usuario = Usuario(
            email=email,
            nombre_completo=nombre_completo,
            password_hash=password_hash,
            rol=rol,
            estado=EstadoUsuario.PENDIENTE_VERIFICACION,
            token_verificacion=token_verificacion,
            ultimo_cambio_password=datetime.utcnow()
        )
        
        self.db.add(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        
        # Log de auditoría
        await self._log_evento_auditoria(
            TipoEventoAuditoria.USUARIO_CREADO,
            f"Usuario registrado exitosamente: {email}",
            usuario_id=str(usuario.id),
            ip_address=ip_address,
            user_agent=user_agent,
            datos_evento={
                "email": email,
                "rol": rol.value,
                "nombre_completo": nombre_completo
            }
        )
        
        return usuario
    
    async def autenticar_usuario(
        self,
        email: str,
        password: str,
        request: Request,
        codigo_mfa: Optional[str] = None
    ) -> Dict[str, Any]:
        """Autentica usuario con MFA opcional."""
        
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        
        usuario = self.db.query(Usuario).filter(Usuario.email == email).first()
        
        # Verificar si el usuario existe
        if not usuario:
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGIN_FALLIDO,
                f"Intento de login con email inexistente: {email}",
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="fallido",
                severidad=NivelSeveridad.WARNING,
                datos_evento={"email": email, "razon": "usuario_inexistente"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        
        # Verificar si puede autenticarse
        if not usuario.puede_autenticarse:
            razon = "usuario_inactivo"
            if usuario.esta_bloqueado:
                razon = "usuario_bloqueado"
            elif not usuario.verificado:
                razon = "email_no_verificado"
            
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGIN_FALLIDO,
                f"Intento de login con usuario no autorizado: {email}",
                usuario_id=str(usuario.id),
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="bloqueado",
                severidad=NivelSeveridad.WARNING,
                datos_evento={"email": email, "razon": razon}
            )
            
            if usuario.esta_bloqueado:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Usuario bloqueado hasta {usuario.bloqueado_hasta}"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no autorizado para acceder"
                )
        
        # Verificar contraseña
        if not self.pwd_context.verify(password, usuario.password_hash):
            usuario.incrementar_intentos_fallidos()
            self.db.commit()
            
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGIN_FALLIDO,
                f"Contraseña incorrecta para usuario: {email}",
                usuario_id=str(usuario.id),
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="fallido",
                severidad=NivelSeveridad.WARNING,
                datos_evento={
                    "email": email,
                    "intentos_fallidos": usuario.intentos_fallidos,
                    "bloqueado": usuario.esta_bloqueado
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        
        # Verificar MFA si está habilitado
        if usuario.mfa_habilitado:
            if not codigo_mfa:
                # Retornar respuesta especial indicando que se requiere MFA
                return {
                    "mfa_required": True,
                    "message": "Código MFA requerido",
                    "usuario_id": str(usuario.id)
                }
            
            if not self._verificar_codigo_mfa(usuario, codigo_mfa):
                await self._log_evento_auditoria(
                    TipoEventoAuditoria.LOGIN_FALLIDO,
                    f"Código MFA incorrecto para usuario: {email}",
                    usuario_id=str(usuario.id),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    resultado="fallido",
                    severidad=NivelSeveridad.WARNING,
                    datos_evento={"email": email, "razon": "mfa_incorrecto"}
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Código MFA inválido"
                )
            
            # Log uso de MFA
            await self._log_evento_auditoria(
                TipoEventoAuditoria.MFA_CODIGO_USADO,
                f"Código MFA usado exitosamente: {email}",
                usuario_id=str(usuario.id),
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        # Reset intentos fallidos y actualizar último acceso
        usuario.resetear_intentos_fallidos()
        usuario.ultimo_acceso = datetime.utcnow()
        usuario.ip_ultimo_acceso = ip_address
        usuario.user_agent_ultimo = user_agent
        
        # Crear sesión
        sesion = await self._crear_sesion(usuario, ip_address, user_agent, request)
        
        # Generar tokens
        access_token = self._crear_access_token(usuario, sesion.token_jti)
        refresh_token = self._crear_refresh_token(usuario, sesion.refresh_token_jti)
        
        self.db.commit()
        
        # Log de login exitoso
        await self._log_evento_auditoria(
            TipoEventoAuditoria.LOGIN_EXITOSO,
            f"Login exitoso para usuario: {email}",
            usuario_id=str(usuario.id),
            sesion_id=str(sesion.id),
            ip_address=ip_address,
            user_agent=user_agent,
            datos_evento={
                "email": email,
                "rol": usuario.rol.value,
                "mfa_usado": usuario.mfa_habilitado
            }
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "usuario": {
                "id": str(usuario.id),
                "email": usuario.email,
                "nombre_completo": usuario.nombre_completo,
                "rol": usuario.rol.value,
                "mfa_habilitado": usuario.mfa_habilitado
            }
        }
    
    async def refresh_token(
        self,
        refresh_token: str,
        request: Request
    ) -> Dict[str, Any]:
        """Renueva el access token usando el refresh token."""
        
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        
        try:
            # Decodificar refresh token
            payload = jwt.decode(
                refresh_token,
                settings.SECRET_KEY,
                algorithms=[self.algoritmo]
            )
            
            usuario_id = payload.get("sub")
            jti = payload.get("jti")
            token_type = payload.get("type")
            
            if not usuario_id or not jti or token_type != "refresh":
                raise JWTError("Token inválido")
            
            # Buscar sesión
            sesion = self.db.query(SesionUsuario).filter(
                SesionUsuario.refresh_token_jti == jti,
                SesionUsuario.activa == True
            ).first()
            
            if not sesion or not sesion.esta_valida:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token inválido o expirado"
                )
            
            # Obtener usuario
            usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
            if not usuario or not usuario.puede_autenticarse:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no autorizado"
                )
            
            # Generar nuevos JTIs
            nuevo_access_jti = str(uuid.uuid4())
            nuevo_refresh_jti = str(uuid.uuid4())
            
            # Actualizar sesión
            sesion.token_jti = nuevo_access_jti
            sesion.refresh_token_jti = nuevo_refresh_jti
            sesion.ultimo_uso = datetime.utcnow()
            
            # Generar nuevos tokens
            access_token = self._crear_access_token(usuario, nuevo_access_jti)
            nuevo_refresh_token = self._crear_refresh_token(usuario, nuevo_refresh_jti)
            
            self.db.commit()
            
            # Log del refresh
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGIN_EXITOSO,
                f"Token renovado para usuario: {usuario.email}",
                usuario_id=str(usuario.id),
                sesion_id=str(sesion.id),
                ip_address=ip_address,
                user_agent=user_agent,
                datos_evento={"tipo": "refresh_token"}
            )
            
            return {
                "access_token": access_token,
                "refresh_token": nuevo_refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
            
        except JWTError as e:
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGIN_FALLIDO,
                f"Intento de refresh con token inválido",
                ip_address=ip_address,
                user_agent=user_agent,
                resultado="fallido",
                severidad=NivelSeveridad.WARNING,
                datos_evento={"error": str(e)}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
    
    async def logout(
        self,
        access_token: str,
        request: Request,
        logout_all_sessions: bool = False
    ) -> Dict[str, str]:
        """Cierra sesión invalidando tokens."""
        
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        
        try:
            # Decodificar access token
            payload = jwt.decode(
                access_token,
                settings.SECRET_KEY,
                algorithms=[self.algoritmo]
            )
            
            usuario_id = payload.get("sub")
            jti = payload.get("jti")
            
            if not usuario_id or not jti:
                raise JWTError("Token inválido")
            
            usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
            
            if logout_all_sessions:
                # Invalidar todas las sesiones del usuario
                sesiones = self.db.query(SesionUsuario).filter(
                    SesionUsuario.usuario_id == usuario_id,
                    SesionUsuario.activa == True
                ).all()
                
                for sesion in sesiones:
                    sesion.invalidar("logout_all")
                
                mensaje = "Todas las sesiones cerradas"
            else:
                # Invalidar solo la sesión actual
                sesion = self.db.query(SesionUsuario).filter(
                    SesionUsuario.token_jti == jti,
                    SesionUsuario.activa == True
                ).first()
                
                if sesion:
                    sesion.invalidar("logout")
                
                mensaje = "Sesión cerrada"
            
            self.db.commit()
            
            # Log del logout
            await self._log_evento_auditoria(
                TipoEventoAuditoria.LOGOUT,
                f"Logout {'completo' if logout_all_sessions else 'parcial'} para usuario: {usuario.email if usuario else 'desconocido'}",
                usuario_id=usuario_id,
                ip_address=ip_address,
                user_agent=user_agent,
                datos_evento={"logout_all": logout_all_sessions}
            )
            
            return {"message": mensaje}
            
        except JWTError:
            # Incluso si el token es inválido, consideramos el logout exitoso
            return {"message": "Sesión cerrada"}
    
    async def habilitar_mfa(
        self,
        usuario_id: str,
        request: Request
    ) -> Dict[str, Any]:
        """Habilita MFA para un usuario y retorna el QR code."""
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if usuario.mfa_habilitado:
            raise HTTPException(
                status_code=400,
                detail="MFA ya está habilitado para este usuario"
            )
        
        # Generar secreto TOTP
        secreto = pyotp.random_base32()
        
        # Cifrar el secreto antes de almacenarlo
        secreto_cifrado = self.cifrado.cifrar_datos(secreto)
        
        # Generar códigos de recuperación
        codigos_recuperacion = [secrets.token_hex(8) for _ in range(10)]
        codigos_cifrados = [self.cifrado.cifrar_datos(codigo) for codigo in codigos_recuperacion]
        
        # Actualizar usuario (pero no habilitar MFA hasta verificar)
        usuario.mfa_secreto = secreto_cifrado
        usuario.codigos_recuperacion = codigos_cifrados
        
        # Generar QR code
        totp = pyotp.TOTP(secreto)
        provisioning_uri = totp.provisioning_uri(
            name=usuario.email,
            issuer_name="Axonote Medical"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convertir a base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        self.db.commit()
        
        # Log de habilitación de MFA (pendiente de verificación)
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        
        await self._log_evento_auditoria(
            TipoEventoAuditoria.MFA_HABILITADO,
            f"MFA configurado (pendiente verificación) para usuario: {usuario.email}",
            usuario_id=str(usuario.id),
            ip_address=ip_address,
            user_agent=user_agent,
            datos_evento={"estado": "pendiente_verificacion"}
        )
        
        return {
            "qr_code": f"data:image/png;base64,{qr_code_base64}",
            "secret": secreto,  # Solo para setup manual
            "backup_codes": codigos_recuperacion,
            "message": "Escanea el código QR y verifica con un código TOTP para completar la configuración"
        }
    
    async def verificar_y_activar_mfa(
        self,
        usuario_id: str,
        codigo_totp: str,
        request: Request
    ) -> Dict[str, str]:
        """Verifica el código TOTP y activa MFA."""
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if usuario.mfa_habilitado:
            raise HTTPException(status_code=400, detail="MFA ya está activo")
        
        if not usuario.mfa_secreto:
            raise HTTPException(status_code=400, detail="MFA no configurado")
        
        # Verificar código TOTP
        if not self._verificar_codigo_mfa(usuario, codigo_totp):
            raise HTTPException(
                status_code=400,
                detail="Código TOTP inválido"
            )
        
        # Activar MFA
        usuario.mfa_habilitado = True
        self.db.commit()
        
        # Log de activación de MFA
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        
        await self._log_evento_auditoria(
            TipoEventoAuditoria.MFA_HABILITADO,
            f"MFA activado exitosamente para usuario: {usuario.email}",
            usuario_id=str(usuario.id),
            ip_address=ip_address,
            user_agent=user_agent,
            datos_evento={"estado": "activo"}
        )
        
        return {"message": "MFA activado exitosamente"}
    
    def _validar_password_seguro(self, password: str) -> bool:
        """Valida que la contraseña cumpla requisitos de seguridad."""
        if len(password) < 12:
            return False
        
        tiene_mayuscula = any(c.isupper() for c in password)
        tiene_minuscula = any(c.islower() for c in password)
        tiene_numero = any(c.isdigit() for c in password)
        tiene_especial = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password)
        
        return all([tiene_mayuscula, tiene_minuscula, tiene_numero, tiene_especial])
    
    def _verificar_codigo_mfa(self, usuario: Usuario, codigo: str) -> bool:
        """Verifica un código MFA (TOTP o código de recuperación)."""
        if not usuario.mfa_secreto:
            return False
        
        # Descifrar secreto
        try:
            secreto = self.cifrado.descifrar_datos(usuario.mfa_secreto)
        except:
            return False
        
        # Verificar código TOTP
        totp = pyotp.TOTP(secreto)
        if totp.verify(codigo, valid_window=1):  # Ventana de 30 segundos antes/después
            return True
        
        # Verificar códigos de recuperación
        if usuario.codigos_recuperacion:
            for codigo_cifrado in usuario.codigos_recuperacion:
                try:
                    codigo_recuperacion = self.cifrado.descifrar_datos(codigo_cifrado)
                    if codigo == codigo_recuperacion:
                        # Remover código usado
                        usuario.codigos_recuperacion.remove(codigo_cifrado)
                        self.db.commit()
                        return True
                except:
                    continue
        
        return False
    
    def _crear_access_token(self, usuario: Usuario, jti: str) -> str:
        """Crea un access token JWT."""
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "sub": str(usuario.id),
            "email": usuario.email,
            "rol": usuario.rol.value,
            "jti": jti,
            "type": "access",
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=self.algoritmo)
    
    def _crear_refresh_token(self, usuario: Usuario, jti: str) -> str:
        """Crea un refresh token JWT."""
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": str(usuario.id),
            "jti": jti,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=self.algoritmo)
    
    async def _crear_sesion(
        self,
        usuario: Usuario,
        ip_address: str,
        user_agent: str,
        request: Request
    ) -> SesionUsuario:
        """Crea una nueva sesión de usuario."""
        
        # Generar JTIs únicos
        token_jti = str(uuid.uuid4())
        refresh_token_jti = str(uuid.uuid4())
        
        # Calcular expiración
        expira_en = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        # Obtener información del dispositivo
        dispositivo_info = {
            "user_agent": user_agent,
            "accept_language": request.headers.get("Accept-Language"),
            "accept_encoding": request.headers.get("Accept-Encoding"),
        }
        
        sesion = SesionUsuario(
            usuario_id=usuario.id,
            token_jti=token_jti,
            refresh_token_jti=refresh_token_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            dispositivo_info=dispositivo_info,
            expira_en=expira_en
        )
        
        self.db.add(sesion)
        self.db.flush()  # Para obtener el ID
        
        # Log de creación de sesión
        await self._log_evento_auditoria(
            TipoEventoAuditoria.SESION_CREADA,
            f"Nueva sesión creada para usuario: {usuario.email}",
            usuario_id=str(usuario.id),
            sesion_id=str(sesion.id),
            ip_address=ip_address,
            user_agent=user_agent,
            datos_evento={
                "sesion_id": str(sesion.id),
                "expira_en": expira_en.isoformat()
            }
        )
        
        return sesion
    
    def _obtener_ip_real(self, request: Request) -> str:
        """Obtiene la IP real considerando proxies y load balancers."""
        # Verificar headers de proxy en orden de prioridad
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Tomar la primera IP (la del cliente original)
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Cloudflare
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        # Fallback a la IP del cliente directo
        return request.client.host if request.client else "unknown"
    
    async def _log_evento_auditoria(
        self,
        tipo_evento: TipoEventoAuditoria,
        descripcion: str,
        usuario_id: Optional[str] = None,
        sesion_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        metodo_http: Optional[str] = None,
        datos_evento: Optional[Dict] = None,
        datos_antes: Optional[Dict] = None,
        datos_despues: Optional[Dict] = None,
        resultado: str = "exitoso",
        severidad: NivelSeveridad = NivelSeveridad.INFO
    ):
        """Registra un evento de auditoría."""
        
        log_entry = LogAuditoria(
            tipo_evento=tipo_evento,
            severidad=severidad,
            descripcion=descripcion,
            resultado=resultado,
            usuario_id=usuario_id,
            sesion_id=sesion_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            metodo_http=metodo_http,
            datos_evento=datos_evento or {},
            datos_antes=datos_antes,
            datos_despues=datos_despues
        )
        
        # Generar hash de integridad
        log_entry.hash_integridad = log_entry.generar_hash_integridad()
        
        self.db.add(log_entry)
        # No hacer commit aquí, se hará en la transacción principal
        
        # Si es un evento crítico, podríamos enviar alertas aquí
        if severidad in [NivelSeveridad.ERROR, NivelSeveridad.CRITICAL]:
            # TODO: Implementar sistema de alertas
            pass
