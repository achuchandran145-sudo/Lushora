import json, hmac, hashlib, os, tempfile
from pathlib import Path
from alembic.config import Config
from alembic import command
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app, _password_hash, _make_token
from app.database import Base, engine, SessionLocal
from app.models import User

client = TestClient(app)

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def test_alembic_initial_migration_creates_schema_and_version(tmp_path, monkeypatch):
    db_path=tmp_path/'migration-smoke.db'
    monkeypatch.setenv('LUSHORA_DATABASE_URL',f'sqlite:///{db_path.as_posix()}')
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.upgrade(config,'head')
    import sqlite3
    connection=sqlite3.connect(db_path)
    try:
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'users' in tables
        assert 'auth_rate_limit_entries' in tables
        assert 'alembic_version' in tables
        revision=connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert revision=='0001_initial'
    finally:
        connection.close()

def test_production_settings_reject_weak_auth_secret(monkeypatch):
    import app.main as main_module
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setattr(main_module, 'AUTH_SECRET', b'development-only-change-this-secret')
    with pytest.raises(RuntimeError, match='LUSHORA_AUTH_SECRET'):
        main_module._validate_production_settings()

def test_production_settings_are_validated_during_startup(monkeypatch):
    import app.main as main_module
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('LUSHORA_AUTH_SECRET', 'weak-secret')
    monkeypatch.setenv('LUSHORA_OTP_DEV_MODE', 'true')
    with pytest.raises(RuntimeError, match='LUSHORA_AUTH_SECRET'):
        main_module.bootstrap_admin_from_environment()


def test_production_settings_reject_missing_cors_origins(monkeypatch):
    import app.main as main_module
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setattr(main_module, 'AUTH_SECRET', b'a' * 40)
    monkeypatch.setattr(main_module, 'OTP_DEV_MODE', False)
    monkeypatch.setattr(main_module, '_CORS_ORIGINS', [])
    with pytest.raises(RuntimeError, match='LUSHORA_CORS_ORIGINS'):
        main_module._validate_production_settings()


def test_admin_bootstrap_rejects_weak_password(monkeypatch):
    import app.main as main_module
    monkeypatch.setenv('LUSHORA_ADMIN_EMAIL','admin-weak@example.com')
    monkeypatch.setenv('LUSHORA_ADMIN_PASSWORD','WeakPassword123')
    with pytest.raises(RuntimeError,match='LUSHORA_ADMIN_PASSWORD'):
        main_module.bootstrap_admin_from_environment()

def test_production_rejects_sqlite_database(monkeypatch):
    import app.main as main_module
    import app.database as database_module
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main_module,'AUTH_SECRET',b'a'*40)
    monkeypatch.setattr(main_module,'OTP_DEV_MODE',False)
    monkeypatch.setattr(main_module,'_CORS_ORIGINS',['https://app.lushora.example'])
    monkeypatch.setattr(database_module,'DATABASE_URL','sqlite:///./lushora.db')
    with pytest.raises(RuntimeError,match='PostgreSQL'):
        main_module._validate_production_settings()

def test_production_rejects_missing_private_storage_and_backup_configuration(monkeypatch):
    import app.main as main_module
    import app.database as database_module
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main_module,'AUTH_SECRET',b'a'*40)
    monkeypatch.setattr(main_module,'OTP_DEV_MODE',False)
    monkeypatch.setattr(main_module,'_CORS_ORIGINS',['https://app.lushora.example'])
    monkeypatch.setattr(database_module,'DATABASE_URL','postgresql+psycopg://user:pass@host/db')
    monkeypatch.delenv('LUSHORA_VERIFICATION_UPLOAD_DIR',raising=False)
    monkeypatch.delenv('LUSHORA_BACKUP_DIR',raising=False)
    monkeypatch.delenv('LUSHORA_BACKUP_RETENTION_DAYS',raising=False)
    with pytest.raises(RuntimeError,match='VERIFICATION_UPLOAD_DIR'):
        main_module._validate_production_settings()

def test_production_rejects_wildcard_cors_origin(monkeypatch):
    import app.main as main_module
    import app.database as database_module
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main_module,'AUTH_SECRET',b'a'*40)
    monkeypatch.setattr(main_module,'OTP_DEV_MODE',False)
    monkeypatch.setattr(main_module,'_CORS_ORIGINS',['https://*.lushora.example'])
    monkeypatch.setattr(database_module,'DATABASE_URL','postgresql+psycopg://user:pass@host/db')
    with pytest.raises(RuntimeError,match='CORS'):
        main_module._validate_production_settings()

def test_demo_seed_disabled_in_production(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    assert client.post('/api/admin/demo-seed').status_code == 404

def test_health_and_categories():
    assert client.get('/api/health').json()['status'] == 'ok'
    assert len(client.get('/api/categories').json()) == 4

def test_seed_and_filter_providers():
    r=client.post('/api/admin/demo-seed')
    assert r.status_code == 200
    providers=client.get('/api/providers',params={'category':'Salon','city':'Coimbatore'}).json()
    assert len(providers)==1
    assert providers[0]['services'][0]['price_inr'] > 0

def test_booking_creation_and_invalid_service():
    client.post('/api/admin/demo-seed')
    p=client.get('/api/providers').json()[0]
    service=p['services'][0]
    payload={'customer_name':'Test Customer','customer_phone':'9876543210','provider_id':p['id'],'service_id':service['id'],'appointment_at':datetime.combine((datetime.now()+timedelta(days=2)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat(),'notes':'Test'}
    r=client.post('/api/bookings',json=payload)
    assert r.status_code==201
    assert r.json()['status']=='requested'
    payload['service_id']=99999
    assert client.post('/api/bookings',json=payload).status_code==404

def test_past_booking_rejected():
    client.post('/api/admin/demo-seed')
    p=client.get('/api/providers').json()[0]
    payload={'customer_name':'Test Customer','customer_phone':'9876543210','provider_id':p['id'],'service_id':p['services'][0]['id'],'appointment_at':(datetime.now()-timedelta(days=1)).isoformat()}
    assert client.post('/api/bookings',json=payload).status_code==400


def test_overlapping_booking_rejected_but_non_overlapping_allowed():
    client.post('/api/admin/demo-seed')
    p = client.get('/api/providers', params={'city':'Coimbatore','category':'Salon'}).json()[0]
    service = p['services'][0]
    start = datetime.combine((datetime.now()+timedelta(days=3)).date(),datetime.strptime('10:00','%H:%M').time())
    payload = {
        'customer_name':'First Customer',
        'customer_phone':'9876543210',
        'provider_id':p['id'],
        'service_id':service['id'],
        'appointment_at':start.isoformat(),
        'notes':''
    }
    first = client.post('/api/bookings', json=payload)
    assert first.status_code == 201
    overlap = payload.copy()
    overlap['customer_name'] = 'Second Customer'
    overlap['appointment_at'] = start.isoformat()
    assert client.post('/api/bookings', json=overlap).status_code == 409
    non_overlap = payload.copy()
    non_overlap['customer_name'] = 'Third Customer'
    non_overlap['appointment_at'] = (start + timedelta(minutes=30)).isoformat()
    assert client.post('/api/bookings', json=non_overlap).status_code == 201


def test_login_rate_limits_after_repeated_bad_passwords():
    client.post('/api/auth/register',json={'full_name':'Rate User','email':'rate-login@example.com','phone':'9876543290','password':'StrongPass123!','role':'customer'})
    for _ in range(5):
        response=client.post('/api/auth/login',json={'email':'rate-login@example.com','password':'wrong-password'})
        assert response.status_code==401
    blocked=client.post('/api/auth/login',json={'email':'rate-login@example.com','password':'StrongPass123!'})
    assert blocked.status_code==429
    assert blocked.headers.get('Retry-After')

def test_login_rate_limit_clears_after_successful_authentication():
    client.post('/api/auth/register',json={'full_name':'Rate User','email':'rate-clear@example.com','phone':'9876543291','password':'StrongPass123!','role':'customer'})
    for _ in range(2):
        assert client.post('/api/auth/login',json={'email':'rate-clear@example.com','password':'wrong-password'}).status_code==401
    success=client.post('/api/auth/login',json={'email':'rate-clear@example.com','password':'StrongPass123!'})
    assert success.status_code==200
    assert client.post('/api/auth/login',json={'email':'rate-clear@example.com','password':'wrong-password'}).status_code==401

def test_registration_rate_limit_by_email():
    payload={'full_name':'Spam User','email':'spam-register@example.com','phone':'9876543292','password':'StrongPass123!','role':'customer'}
    first=client.post('/api/auth/register',json=payload)
    assert first.status_code==201
    # Duplicate registration responses still consume the email-scoped attempt budget.
    for _ in range(4):
        assert client.post('/api/auth/register',json=payload).status_code==409
    blocked=client.post('/api/auth/register',json=payload)
    assert blocked.status_code==429

def test_otp_request_rate_limit_by_phone_and_ip():
    phone='9876543293'
    # Avoid the 60-second resend cooldown by removing challenge rows between calls;
    # the persistent rate limiter still tracks the hourly/daily quotas.
    for _ in range(3):
        response=client.post('/api/v2/customer/otp/request',json={'phone':phone})
        assert response.status_code==200
        from app.database import SessionLocal
        db=SessionLocal()
        try:
            db.query(__import__('app.models',fromlist=['OTPChallenge']).OTPChallenge).filter_by(phone='+91'+phone).delete()
            db.commit()
        finally:
            db.close()
    blocked=client.post('/api/v2/customer/otp/request',json={'phone':phone})
    assert blocked.status_code==429

def test_otp_verify_attempts_are_limited_and_challenge_consumed():
    request=client.post('/api/v2/customer/otp/request',json={'phone':'9876543294'})
    assert request.status_code==200
    otp=request.json()['development_otp']
    for _ in range(5):
        assert client.post('/api/v2/customer/otp/verify',json={'phone':'9876543294','otp':'000000' if otp!='000000' else '000001'}).status_code==401
    blocked=client.post('/api/v2/customer/otp/verify',json={'phone':'9876543294','otp':otp})
    assert blocked.status_code==429

def test_registration_rejects_weak_passwords():
    weak_passwords=['short1A!','alllowercase123!','ALLUPPERCASE123!','NoDigitsHere!!','NoSpecial12345']
    for index,password in enumerate(weak_passwords):
        response=client.post('/api/auth/register',json={'full_name':'Weak Password','email':f'weak-{index}@example.com','phone':'9876543300','password':password,'role':'customer'})
        assert response.status_code==422

def test_logout_revokes_existing_access_token():
    registration=client.post('/api/auth/register',json={'full_name':'Logout User','email':'logout-user@example.com','phone':'9876543301','password':'StrongPass123!!','role':'customer'})
    token=registration.json()['access_token']
    headers={'Authorization':f'Bearer {token}'}
    assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.post('/api/auth/logout',headers=headers).status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==401
    re_login=client.post('/api/auth/login',json={'email':'logout-user@example.com','password':'StrongPass123!!'})
    assert re_login.status_code==200
    assert client.get('/api/auth/me',headers={'Authorization':f"Bearer {re_login.json()['access_token']}"}).status_code==200

def test_token_claims_require_issuer_and_version():
    import app.main as main_module
    db=SessionLocal()
    try:
        user=User(full_name='Token User',email='token-user@example.com',phone='',password_hash=_password_hash('StrongPass123!!'),role='customer')
        db.add(user);db.commit();db.refresh(user)
        valid=main_module._make_token(user.id,user.auth_token_version)
        assert main_module._get_user_from_token(valid,db) is not None
        user.auth_token_version += 1;db.commit()
        assert main_module._get_user_from_token(valid,db) is None
    finally:
        db.close()

def test_verification_upload_rejects_fake_mime_file():
    reg=client.post('/api/auth/register',json={'full_name':'Upload Provider','email':'upload-provider@example.com','phone':'9876543340','password':'StrongPass123!','role':'provider'})
    headers={'Authorization':f"Bearer {reg.json()['access_token']}"}
    submission=client.post('/api/v2/provider/verification/submit',headers=headers,json={'business_name':'Upload Salon','city':'Coimbatore','locality':'Vadavalli','address':'Test address','categories':['Salon']})
    assert submission.status_code==201
    fake=client.post('/api/v2/provider/verification/document/pan',headers=headers,files={'file':('fake.png',b'not an image', 'image/png')})
    assert fake.status_code==400

def test_verification_upload_rejects_invalid_pdf_signature():
    reg=client.post('/api/auth/register',json={'full_name':'Upload Provider','email':'upload-provider-pdf@example.com','phone':'9876543341','password':'StrongPass123!','role':'provider'})
    headers={'Authorization':f"Bearer {reg.json()['access_token']}"}
    submission=client.post('/api/v2/provider/verification/submit',headers=headers,json={'business_name':'Upload Salon PDF','city':'Coimbatore','locality':'Vadavalli','address':'Test address','categories':['Salon']})
    assert submission.status_code==201
    fake=client.post('/api/v2/provider/verification/document/business',headers=headers,files={'file':('fake.pdf',b'not a pdf', 'application/pdf')})
    assert fake.status_code==400

def test_expired_and_tampered_tokens_are_rejected():
    import app.main as main_module
    db=SessionLocal()
    try:
        user=User(full_name='Token Guard',email='token-guard@example.com',phone='',password_hash=_password_hash('StrongPass123!'),role='customer')
        db.add(user);db.commit();db.refresh(user)
        now=int(datetime.utcnow().timestamp())
        payload=main_module._b64(json.dumps({'sub':user.id,'iat':now-3600,'exp':now-10,'iss':'lushora-api','v':0,'jti':'expired'}).encode())
        signature=main_module._b64(hmac.new(main_module.AUTH_SECRET,payload.encode(),hashlib.sha256).digest())
        assert main_module._get_user_from_token(payload+'.'+signature,db) is None
        valid=main_module._make_token(user.id,user.auth_token_version)
        payload_part,signature_part=valid.split('.')
        tampered=payload_part+'.'+signature_part[:-1]+'X'
        assert main_module._get_user_from_token(tampered,db) is None
    finally:
        db.close()

def test_failed_login_creates_privacy_preserving_audit_event_and_admin_route_is_role_protected():
    import app.main as main_module
    client.post('/api/auth/register',json={'full_name':'Audit User','email':'audit-user@example.com','phone':'9876543342','password':'StrongPass123!','role':'customer'})
    assert client.post('/api/auth/login',json={'email':'audit-user@example.com','password':'wrong-password'}).status_code==401
    customer=client.post('/api/auth/login',json={'email':'audit-user@example.com','password':'StrongPass123!'})
    assert customer.status_code==200
    customer_headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    assert client.get('/api/admin/security/audit',headers=customer_headers).status_code==403
    db=SessionLocal()
    try:
        event=db.query(__import__('app.models',fromlist=['SecurityAuditEvent']).SecurityAuditEvent).filter_by(event_type='login_failed').first()
        assert event is not None
        assert event.identifier_hash and len(event.identifier_hash)==64
        assert 'audit-user@example.com' not in event.identifier_hash
        admin=User(full_name='Audit Admin',email='audit-admin@example.com',phone='',password_hash=_password_hash('StrongPass123!'),role='admin')
        db.add(admin);db.commit();db.refresh(admin)
        admin_token=main_module._make_token(admin.id,admin.auth_token_version)
    finally:
        db.close()
    response=client.get('/api/admin/security/audit',headers={'Authorization':f'Bearer {admin_token}'})
    assert response.status_code==200
    assert any(item['event_type']=='login_failed' for item in response.json())

def test_sqlite_migration_deduplicates_and_uniquifies_auth_rate_limits(tmp_path,monkeypatch):
    from sqlalchemy import create_engine,text,inspect
    import app.database as database_module
    legacy_engine=create_engine(f"sqlite:///{(tmp_path/'legacy-auth.db').as_posix()}")
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, full_name VARCHAR(120), email VARCHAR(255), phone VARCHAR(30), password_hash VARCHAR(255), role VARCHAR(20), is_active BOOLEAN)"))
        connection.execute(text("CREATE TABLE auth_rate_limit_entries (id INTEGER PRIMARY KEY, scope VARCHAR(40) NOT NULL, identifier_hash VARCHAR(64) NOT NULL, window_started_at DATETIME NOT NULL, attempts INTEGER NOT NULL, blocked_until DATETIME)"))
        connection.execute(text("INSERT INTO auth_rate_limit_entries (scope,identifier_hash,window_started_at,attempts) VALUES ('login','hashed-key','2026-01-01 00:00:00',2),('login','hashed-key','2026-01-01 00:00:00',4)"))
    monkeypatch.setattr(database_module,'engine',legacy_engine)
    monkeypatch.setattr(database_module,'DATABASE_URL','sqlite://')
    database_module.migrate_sqlite_schema()
    with legacy_engine.connect() as connection:
        rows=connection.execute(text("SELECT scope,identifier_hash,attempts FROM auth_rate_limit_entries")).all()
        assert len(rows)==1
        indexes=inspect(legacy_engine).get_indexes('auth_rate_limit_entries')
        assert any(index['name']=='uq_auth_rate_limit_scope_identifier' and index['unique'] for index in indexes)
    legacy_engine.dispose()

def test_customer_register_login_and_me():
    registration = client.post('/api/auth/register', json={'full_name':'Test User','email':'test-user@example.com','phone':'9876543210','password':'StrongPass123!','role':'customer'})
    assert registration.status_code == 201
    token = registration.json()['access_token']
    profile = client.get('/api/auth/me', headers={'Authorization':f'Bearer {token}'})
    assert profile.status_code == 200
    assert profile.json()['role'] == 'customer'
    login = client.post('/api/auth/login', json={'email':'test-user@example.com','password':'StrongPass123!'})
    assert login.status_code == 200
    assert client.post('/api/auth/login', json={'email':'test-user@example.com','password':'wrongpass'}).status_code == 401


def test_provider_registration_is_pending():
    registration = client.post('/api/auth/register', json={'full_name':'Provider User','email':'provider-user@example.com','phone':'9876543211','password':'StrongPass123!','role':'provider'})
    assert registration.status_code == 201
    token = registration.json()['access_token']
    submission = client.post('/api/provider/register', headers={'Authorization':f'Bearer {token}'}, json={'name':'New Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Test business'})
    assert submission.status_code == 201
    assert submission.json()['approval_status'] == 'pending'
    assert len(client.get('/api/providers').json()) == 0

def test_notification_preferences_default_external_channels_off():
    registration=client.post('/api/auth/register',json={'full_name':'Notify User','email':'notify-default@example.com','phone':'9876543212','password':'StrongPass123!','role':'customer'})
    token=registration.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    prefs=client.get('/api/me/notification-preferences',headers=headers)
    assert prefs.status_code==200
    assert prefs.json()=={'in_app_enabled':True,'push_enabled':False,'whatsapp_enabled':False,'sms_enabled':False}

def test_notification_preferences_validate_and_opt_in_opt_out():
    registration=client.post('/api/auth/register',json={'full_name':'Notify User','email':'notify-opt@example.com','phone':'9876543213','password':'StrongPass123!','role':'customer'})
    token=registration.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    invalid=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':'yes'})
    assert invalid.status_code==400
    opted=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':True,'whatsapp_enabled':True})
    assert opted.status_code==200 and opted.json()['sms_enabled'] is True and opted.json()['whatsapp_enabled'] is True
    opted_out=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':False})
    assert opted_out.status_code==200 and opted_out.json()['sms_enabled'] is False and opted_out.json()['whatsapp_enabled'] is True

def test_provider_owner_can_register_multiple_categories_but_not_duplicate_category():
    registration = client.post('/api/auth/register', json={'full_name':'Multi Category Provider','email':'multi-provider@example.com','phone':'9876543220','password':'StrongPass123!','role':'provider'})
    assert registration.status_code == 201
    token = registration.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    salon = {'name':'Multi Beauty Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Salon listing'}
    nail = {**salon,'category':'Nail Studio','description':'Nail listing'}
    first = client.post('/api/provider/register',headers=headers,json=salon)
    second = client.post('/api/provider/register',headers=headers,json=nail)
    duplicate = client.post('/api/provider/register',headers=headers,json=salon)
    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate.status_code == 409
    rows = client.get('/api/providers').json()
    assert len(rows) == 0  # Pending listings are not public

def test_customer_profile_requires_auth_and_validates_supported_city():
    assert client.get('/api/v2/customer/profile').status_code == 401
    registration = client.post('/api/auth/register', json={'full_name':'Profile Test','email':'profile-test@example.com','phone':'9876543230','password':'StrongPass123!','role':'customer'})
    headers = {'Authorization': f"Bearer {registration.json()['access_token']}"}
    assert client.get('/api/v2/customer/profile', headers=headers).status_code == 200
    incomplete = {'first_name':'Profile','last_name':'Test','street_address':'12 Test Street','city':'Coimbatore','locality':''}
    assert client.patch('/api/v2/customer/profile',headers=headers,json=incomplete).status_code == 400
    unsupported = {**incomplete,'locality':'Vadavalli','city':'Madurai'}
    assert client.patch('/api/v2/customer/profile',headers=headers,json=unsupported).status_code == 400
    valid = {**incomplete,'locality':'Vadavalli'}
    saved = client.patch('/api/v2/customer/profile',headers=headers,json=valid)
    assert saved.status_code == 200
    assert saved.json()['profile_complete'] is True
    assert saved.json()['city'] == 'Coimbatore'
    assert client.get('/api/v2/customer/profile',headers=headers).json()['street_address'] == '12 Test Street'

def test_provider_availability_validation_and_owner_access():
    provider_reg = client.post('/api/auth/register',json={'full_name':'Availability Provider','email':'availability-provider@example.com','phone':'9876543231','password':'StrongPass123!','role':'provider'})
    headers = {'Authorization':f"Bearer {provider_reg.json()['access_token']}"}
    listing = client.post('/api/provider/register',headers=headers,json={'name':'Availability Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Test'})
    assert listing.status_code == 201
    invalid_days = client.put('/api/provider/me/availability',headers=headers,json={'working_days':[8],'start_time':'09:00','end_time':'18:00'})
    assert invalid_days.status_code == 400
    invalid_hours = client.put('/api/provider/me/availability',headers=headers,json={'working_days':[0,1],'start_time':'18:00','end_time':'09:00'})
    assert invalid_hours.status_code == 400
    valid = client.put('/api/provider/me/availability',headers=headers,json={'working_days':[0,1,2,3,4],'start_time':'09:00','end_time':'18:00','break_start':'13:00','break_end':'14:00'})
    assert valid.status_code == 200
    assert valid.json()['working_days'] == [0,1,2,3,4]

def test_reviews_require_completed_owned_booking_and_moderation():
    customer = client.post('/api/auth/register',json={'full_name':'Review Customer','email':'review-customer@example.com','phone':'9876543240','password':'StrongPass123!','role':'customer'})
    customer_headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    client.post('/api/admin/demo-seed')
    provider=client.get('/api/providers',params={'category':'Salon','city':'Coimbatore'}).json()[0]
    service=provider['services'][0]
    booking_payload={'customer_name':'Review Customer','customer_phone':'9876543240','provider_id':provider['id'],'service_id':service['id'],'appointment_at':datetime.combine((datetime.now()+timedelta(days=4)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat(),'notes':'Review test'}
    booking=client.post('/api/bookings',headers=customer_headers,json=booking_payload)
    assert booking.status_code==201
    not_completed=client.post('/api/customer/me/reviews',headers=customer_headers,json={'booking_id':booking.json()['id'],'rating':5,'comment':'Good'})
    assert not_completed.status_code==400
    # Set completed state through the test DB, then validate review submission rules.
    from app.database import get_db
    from app import models
    db=next(get_db())
    try:
        row=db.query(models.Booking).filter(models.Booking.id==booking.json()['id']).first()
        row.status='completed'
        db.commit()
    finally:
        db.close()
    invalid_rating=client.post('/api/customer/me/reviews',headers=customer_headers,json={'booking_id':booking.json()['id'],'rating':6,'comment':'Invalid'})
    assert invalid_rating.status_code==400
    created=client.post('/api/customer/me/reviews',headers=customer_headers,json={'booking_id':booking.json()['id'],'rating':5,'comment':'Great experience'})
    assert created.status_code==201
    duplicate=client.post('/api/customer/me/reviews',headers=customer_headers,json={'booking_id':booking.json()['id'],'rating':4,'comment':'Again'})
    assert duplicate.status_code==409
    assert client.get(f"/api/providers/{provider['id']}/reviews").json()['review_count']==0 # pending moderation

def test_provider_service_edit_owner_validation():
    reg=client.post('/api/auth/register',json={'full_name':'Service Owner','email':'service-owner@example.com','phone':'9876543250','password':'StrongPass123!','role':'provider'})
    headers={'Authorization':f"Bearer {reg.json()['access_token']}"}
    from app.database import get_db
    from app import models
    db=next(get_db())
    try:
        user=db.query(models.User).filter(models.User.email=='service-owner@example.com').first()
        provider=models.Provider(owner_user_id=user.id,name='Edit Service Studio',category='Salon',city='Coimbatore',locality='Vadavalli',description='Test',approval_status='approved',verified=True)
        db.add(provider);db.flush()
        service=models.Service(provider_id=provider.id,name='Haircut',price_inr=500,duration_minutes=30)
        db.add(service);db.commit();service_id=service.id
        foreign=models.Provider(name='Foreign Studio',category='Salon',city='Coimbatore',locality='Vadavalli',description='Other',approval_status='approved')
        db.add(foreign);db.flush()
        foreign_service=models.Service(provider_id=foreign.id,name='Other service',price_inr=100,duration_minutes=20)
        db.add(foreign_service);db.commit();foreign_service_id=foreign_service.id
    finally: db.close()
    edited=client.patch(f'/api/provider/me/services/{service_id}',headers=headers,json={'name':'Premium Haircut','price_inr':750,'duration_minutes':45})
    assert edited.status_code==200
    assert edited.json()['name']=='Premium Haircut'
    assert edited.json()['price_inr']==750
    assert edited.json()['duration_minutes']==45
    assert client.patch(f'/api/provider/me/services/{service_id}',headers=headers,json={'price_inr':-1}).status_code==400
    assert client.patch(f'/api/provider/me/services/{foreign_service_id}',headers=headers,json={'name':'Hijacked'}).status_code==404

def test_booking_cancellation_requires_owner_and_allowed_state():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Cancel Owner','email':'cancel-owner@example.com','phone':'9876543260','password':'StrongPass123!','role':'customer'})
    token=customer.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    provider=client.get('/api/providers').json()[0];service=provider['services'][0]
    payload={'customer_name':'Cancel Owner','customer_phone':'9876543260','provider_id':provider['id'],'service_id':service['id'],'appointment_at':datetime.combine((datetime.now()+timedelta(days=5)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat(),'notes':''}
    booking=client.post('/api/bookings',headers=headers,json=payload)
    assert booking.status_code==201
    booking_id=booking.json()['id']
    stranger=client.post('/api/auth/register',json={'full_name':'Cancel Stranger','email':'cancel-stranger@example.com','phone':'9876543261','password':'StrongPass123!','role':'customer'})
    stranger_headers={'Authorization':f"Bearer {stranger.json()['access_token']}"}
    assert client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=stranger_headers).status_code==403
    cancelled=client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=headers)
    assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    assert client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=headers).status_code==400

def test_booking_enforces_provider_schedule_break_and_closed_dates():
    from app.database import get_db
    from app import models
    provider_reg=client.post('/api/auth/register',json={'full_name':'Schedule Provider','email':'schedule-provider@example.com','phone':'9876543270','password':'StrongPass123!','role':'provider'})
    provider_headers={'Authorization':f"Bearer {provider_reg.json()['access_token']}"}
    listing=client.post('/api/provider/register',headers=provider_headers,json={'name':'Schedule Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Test'})
    assert listing.status_code==201
    db=next(get_db())
    try:
        owner=db.query(models.User).filter(models.User.email=='schedule-provider@example.com').first()
        provider=db.query(models.Provider).filter(models.Provider.owner_user_id==owner.id).first()
        service=models.Service(provider_id=provider.id,name='Schedule Service',price_inr=500,duration_minutes=60)
        db.add(service);db.flush();provider_id=provider.id;service_id=service.id
        day=(datetime.now()+timedelta(days=7)).date()
        provider.availability_config='{"working_days":[],"start_time":"09:00","end_time":"18:00","break_start":"13:00","break_end":"14:00","closed_dates":[]}'
        db.commit()
    finally: db.close()
    payload={'customer_name':'Schedule Customer','customer_phone':'9876543271','provider_id':provider_id,'service_id':service_id,'appointment_at':datetime.combine(day,datetime.strptime('10:00','%H:%M').time()).isoformat(),'notes':''}
    assert client.post('/api/bookings',json=payload).status_code==400
    db=next(get_db())
    try:
        provider=db.query(models.Provider).filter(models.Provider.id==provider_id).first()
        provider.availability_config=json.dumps({'working_days':[day.weekday()],'start_time':'09:00','end_time':'18:00','break_start':'13:00','break_end':'14:00','closed_dates':[day.isoformat()]})
        db.commit()
    finally: db.close()
    assert client.post('/api/bookings',json=payload).status_code==400
    db=next(get_db())
    try:
        provider=db.query(models.Provider).filter(models.Provider.id==provider_id).first()
        provider.availability_config=json.dumps({'working_days':[day.weekday()],'start_time':'09:00','end_time':'18:00','break_start':'13:00','break_end':'14:00','closed_dates':[]})
        db.commit()
    finally: db.close()
    payload['appointment_at']=datetime.combine(day,datetime.strptime('13:30','%H:%M').time()).isoformat()
    assert client.post('/api/bookings',json=payload).status_code==400
    payload['appointment_at']=datetime.combine(day,datetime.strptime('17:30','%H:%M').time()).isoformat()
    assert client.post('/api/bookings',json=payload).status_code==400
    payload['appointment_at']=datetime.combine(day,datetime.strptime('10:00','%H:%M').time()).isoformat()
    assert client.post('/api/bookings',json=payload).status_code==201

def test_booking_status_transition_matrix_and_role_permissions():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Lifecycle Customer','email':'lifecycle-customer@example.com','phone':'9876543280','password':'StrongPass123!','role':'customer'})
    provider_user=client.post('/api/auth/register',json={'full_name':'Lifecycle Provider','email':'lifecycle-provider@example.com','phone':'9876543281','password':'StrongPass123!','role':'provider'})
    customer_headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    provider_headers={'Authorization':f"Bearer {provider_user.json()['access_token']}"}
    # Customer must not be able to confirm or reject their own booking.
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    appointment=datetime.combine((datetime.now()+timedelta(days=6)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    payload={'customer_name':'Lifecycle Customer','customer_phone':'9876543280','provider_id':p['id'],'service_id':service['id'],'appointment_at':appointment,'notes':''}
    booking=client.post('/api/bookings',headers=customer_headers,json=payload)
    assert booking.status_code==201
    bid=booking.json()['id']
    assert client.patch(f'/api/bookings/{bid}/status?status=confirmed',headers=customer_headers).status_code==403
    assert client.patch(f'/api/bookings/{bid}/status?status=rejected',headers=customer_headers).status_code==403
    # Provider role with no business ownership is not allowed to update this booking.
    assert client.patch(f'/api/bookings/{bid}/status?status=rejected',headers=provider_headers).status_code==403
    # Completion is not allowed from requested state.
    assert client.patch(f'/api/bookings/{bid}/status?status=completed',headers=provider_headers).status_code==403
    # A rejection is terminal; it cannot subsequently be confirmed.
    assert client.patch(f'/api/bookings/{bid}/status?status=rejected',headers=provider_headers).status_code==403
    assert client.patch(f'/api/bookings/{bid}/status?status=confirmed',headers=customer_headers).status_code==403

def test_payment_record_is_owner_scoped_and_idempotent_pending_only():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Payment Owner','email':'pay-owner@example.com','phone':'9876543290','password':'StrongPass123!','role':'customer'})
    stranger=client.post('/api/auth/register',json={'full_name':'Payment Stranger','email':'pay-stranger@example.com','phone':'9876543291','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    stranger_headers={'Authorization':f"Bearer {stranger.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=8)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Payment Owner','customer_phone':'9876543290','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    first=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'test-idem-paymentkey0001'})
    assert first.status_code==201 and first.json()['status']=='pending'
    second=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'test-idem-paymentkey0001'})
    assert second.json()['id']==first.json()['id']
    denied=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':stranger_headers['Authorization'],'Idempotency-Key':'test-idem-strangerkey0001'})
    assert denied.status_code==404
    assert client.get('/api/payments/me',headers=headers).status_code==200

def test_cancel_booking_cancels_pending_payment_record():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Cancel Pay Customer','email':'cancel-pay@example.com','phone':'9876543292','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=9)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Cancel Pay Customer','customer_phone':'9876543292','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    pay=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'test-idem-cancelpayment0001'})
    assert pay.status_code==201 and pay.json()['status']=='pending'
    cancelled=client.patch(f'/api/bookings/{bid}/status?status=cancelled',headers=headers)
    assert cancelled.status_code==200
    history=client.get('/api/payments/me',headers=headers)
    record=next(x for x in history.json() if x['id']==pay.json()['id'])
    assert record['status']=='cancelled'

def test_payment_rejects_second_pending_record_with_different_key():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Duplicate Payment Customer','email':'duplicate-pay@example.com','phone':'9876543293','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=10)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Duplicate Payment Customer','customer_phone':'9876543293','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    first=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'test-idem-duppayment0001'})
    assert first.status_code==201
    second=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'test-idem-duppayment0002'})
    assert second.status_code==409

def test_admin_payment_list_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Payments Admin Guard','email':'payments-admin-guard@example.com','phone':'9876543294','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments',headers=headers)
    assert response.status_code==403

def test_admin_payment_summary_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Payment Summary Guard','email':'payment-summary-guard@example.com','phone':'9876543295','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments/summary',headers=headers)
    assert response.status_code==403

def test_admin_payment_reconciliation_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Recon Guard','email':'recon-guard@example.com','phone':'9876543296','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments/reconciliation',headers=headers)
    assert response.status_code==403


def test_refund_request_and_admin_review_foundation():
    client.post('/api/admin/demo-seed')
    cust=client.post('/api/auth/register',json={'full_name':'Refund Customer','email':'refund-customer@example.com','phone':'9876543217','password':'StrongPass123!','role':'customer'})
    session=SessionLocal()
    admin_user=User(full_name='Refund Admin',email='refund-admin@example.com',phone='9876543218',password_hash=_password_hash('StrongPass123!'),role='admin',is_active=True)
    session.add(admin_user); session.commit(); session.refresh(admin_user); admin_token=_make_token(admin_user.id); session.close()
    cust_headers={'Authorization':f"Bearer {cust.json()['access_token']}"}
    admin_headers={'Authorization':f"Bearer {admin_token}"}
    p=client.get('/api/providers').json()[0]; service=p['services'][0]
    appt=datetime.combine((datetime.now()+timedelta(days=11)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=cust_headers,json={'customer_name':'Refund Customer','customer_phone':'9876543217','provider_id':p['id'],'service_id':service['id'],'appointment_at':appt,'notes':''})
    payment=client.post('/api/payments',headers={**cust_headers,'Idempotency-Key':'test-idem-refundpayment001'},json={'booking_id':booking.json()['id']})
    assert payment.status_code==201
    from app.models import Payment
    from app.database import get_db
    db=next(get_db())
    record=db.query(Payment).filter(Payment.id==payment.json()['id']).first(); record.status='paid'; db.commit(); db.close()
    requested=client.post('/api/refunds',headers=cust_headers,json={'payment_id':payment.json()['id'],'reason':'Booking cancelled','amount_inr':payment.json()['amount_inr']})
    assert requested.status_code==201 and requested.json()['status']=='requested'
    duplicate=client.post('/api/refunds',headers=cust_headers,json={'payment_id':payment.json()['id'],'reason':'Duplicate','amount_inr':payment.json()['amount_inr']})
    assert duplicate.status_code==409
    customer_denied=client.get('/api/admin/refunds',headers=cust_headers)
    assert customer_denied.status_code==403
    approved=client.patch(f"/api/admin/refunds/{requested.json()['id']}/review",headers=admin_headers,json={'status':'approved','reviewer_note':'Reviewed manually'})
    assert approved.status_code==200 and approved.json()['status']=='approved'
    processing=client.patch(f"/api/admin/refunds/{requested.json()['id']}/review",headers=admin_headers,json={'status':'processed'})
    assert processing.status_code==400
    assert client.get('/api/refunds/me',headers=cust_headers).status_code==200


def test_provider_owner_profile_edit_and_isolation():
    reg1=client.post('/api/auth/register',json={'full_name':'Profile Provider One','email':'profile-provider-one@example.com','phone':'9876543301','password':'StrongPass123!','role':'provider'})
    reg2=client.post('/api/auth/register',json={'full_name':'Profile Provider Two','email':'profile-provider-two@example.com','phone':'9876543302','password':'StrongPass123!','role':'provider'})
    h1={'Authorization':f"Bearer {reg1.json()['access_token']}"}
    h2={'Authorization':f"Bearer {reg2.json()['access_token']}"}
    p1=client.post('/api/provider/register',headers=h1,json={'name':'One Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Initial'})
    p2=client.post('/api/provider/register',headers=h2,json={'name':'Two Studio','category':'Salon','city':'Chennai','locality':'Adyar','description':'Initial'})
    assert p1.status_code==201 and p2.status_code==201
    updated=client.patch('/api/provider/me/profile',headers=h1,json={'name':'One Premium Studio','description':'Updated business profile','city':'Coimbatore','locality':'RS Puram'})
    assert updated.status_code==200
    assert updated.json()['name']=='One Premium Studio'
    assert updated.json()['locality']=='RS Puram'
    foreign=client.patch('/api/provider/me/profile',headers=h1,json={'provider_id':p2.json()['id'],'name':'Hijacked','city':'Chennai','locality':'Adyar'})
    assert foreign.status_code==404
    invalid=client.patch('/api/provider/me/profile',headers=h1,json={'city':'Madurai','locality':'Central'})
    assert invalid.status_code==400
    blank=client.patch('/api/provider/me/profile',headers=h1,json={'name':' ','locality':'Vadavalli'})
    assert blank.status_code==400


def test_customer_profile_edit_validation_and_owner_scope():
    reg=client.post('/api/auth/register',json={'full_name':'Profile Customer','email':'profile-customer@example.com','phone':'9876543303','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {reg.json()['access_token']}"}
    saved=client.patch('/api/v2/customer/profile',headers=headers,json={'first_name':'Chandran','last_name':'User','street_address':'12 Main Road','city':'Coimbatore','locality':'Vadavalli'})
    assert saved.status_code==200
    assert saved.json()['profile_complete'] is True
    assert client.get('/api/v2/customer/profile',headers=headers).json()['street_address']=='12 Main Road'
    invalid_city=client.patch('/api/v2/customer/profile',headers=headers,json={'first_name':'Chandran','last_name':'User','street_address':'12 Main Road','city':'Madurai','locality':'Central'})
    assert invalid_city.status_code==400
    too_long=client.patch('/api/v2/customer/profile',headers=headers,json={'first_name':'A'*81,'last_name':'User','street_address':'12 Main Road','city':'Coimbatore','locality':'Vadavalli'})
    assert too_long.status_code==400
    missing=client.patch('/api/v2/customer/profile',headers=headers,json={'first_name':'Chandran','last_name':'User','street_address':'','city':'Coimbatore','locality':'Vadavalli'})
    assert missing.status_code==400
    other=client.post('/api/auth/register',json={'full_name':'Other Customer','email':'other-profile-customer@example.com','phone':'9876543304','password':'StrongPass123!','role':'customer'})
    other_headers={'Authorization':f"Bearer {other.json()['access_token']}"}
    assert client.get('/api/v2/customer/profile',headers=other_headers).json()['profile_complete'] is False


def test_provider_availability_closure_dates_validation_and_normalization():
    reg=client.post('/api/auth/register',json={'full_name':'Availability Owner','email':'availability-owner@example.com','phone':'9876543305','password':'StrongPass123!','role':'provider'})
    headers={'Authorization':f"Bearer {reg.json()['access_token']}"}
    created=client.post('/api/provider/register',headers=headers,json={'name':'Availability Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':''})
    assert created.status_code==201
    valid=client.put('/api/provider/me/availability',headers=headers,json={'working_days':[0,1,1,5],'start_time':'09:00','end_time':'18:00','break_start':'13:00','break_end':'14:00','closed_dates':['2026-12-25','2026-12-25']})
    assert valid.status_code==200
    assert valid.json()['working_days']==[0,1,5]
    assert valid.json()['closed_dates']==['2026-12-25']
    invalid_date=client.put('/api/provider/me/availability',headers=headers,json={'working_days':[0],'start_time':'09:00','end_time':'18:00','closed_dates':['25-12-2026']})
    assert invalid_date.status_code==400
    invalid_type=client.put('/api/provider/me/availability',headers=headers,json={'working_days':[0],'start_time':'09:00','end_time':'18:00','closed_dates':'2026-12-25'})
    assert invalid_type.status_code==400


def test_provider_portfolio_upload_validation_and_owner_isolation():
    from io import BytesIO
    from PIL import Image
    reg1=client.post('/api/auth/register',json={'full_name':'Gallery Owner One','email':'gallery-one@example.com','phone':'9876543306','password':'StrongPass123!','role':'provider'})
    reg2=client.post('/api/auth/register',json={'full_name':'Gallery Owner Two','email':'gallery-two@example.com','phone':'9876543307','password':'StrongPass123!','role':'provider'})
    h1={'Authorization':f"Bearer {reg1.json()['access_token']}"};h2={'Authorization':f"Bearer {reg2.json()['access_token']}"}
    p1=client.post('/api/provider/register',headers=h1,json={'name':'Gallery Studio One','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':''})
    p2=client.post('/api/provider/register',headers=h2,json={'name':'Gallery Studio Two','category':'Salon','city':'Chennai','locality':'Adyar','description':''})
    image_bytes=BytesIO();Image.new('RGB',(40,40),'white').save(image_bytes,format='PNG');image_bytes.seek(0)
    upload=client.post('/api/provider/me/portfolio',headers=h1,files={'file':('portfolio.png',image_bytes.getvalue(),'image/png')},data={'caption':'Studio work'})
    assert upload.status_code==201
    image_id=upload.json()['id']
    assert client.get('/api/provider/me/portfolio',headers=h1).json()[0]['caption']=='Studio work'
    public=client.get(upload.json()['image_url'])
    assert public.status_code==200 and public.headers['content-type'].startswith('image/')
    invalid=client.post('/api/provider/me/portfolio',headers=h1,files={'file':('bad.jpg',b'not-an-image','image/jpeg')})
    assert invalid.status_code==400
    foreign_delete=client.delete(f'/api/provider/me/portfolio/{image_id}',headers=h2)
    assert foreign_delete.status_code==404
    deleted=client.delete(f'/api/provider/me/portfolio/{image_id}',headers=h1)
    assert deleted.status_code==200
    assert client.get(upload.json()['image_url']).status_code==404


def test_provider_staff_management_validation_and_owner_isolation():
    r1=client.post('/api/auth/register',json={'full_name':'Staff Owner One','email':'staff-owner-one@example.com','phone':'9876543308','password':'StrongPass123!','role':'provider'})
    r2=client.post('/api/auth/register',json={'full_name':'Staff Owner Two','email':'staff-owner-two@example.com','phone':'9876543309','password':'StrongPass123!','role':'provider'})
    h1={'Authorization':f"Bearer {r1.json()['access_token']}"};h2={'Authorization':f"Bearer {r2.json()['access_token']}"}
    for headers,name,city,loc in [(h1,'Staff Provider One','Coimbatore','Vadavalli'),(h2,'Staff Provider Two','Chennai','Adyar')]:
        assert client.post('/api/provider/register',headers=headers,json={'name':name,'category':'Salon','city':city,'locality':loc,'description':''}).status_code==201
    created=client.post('/api/provider/me/staff',headers=h1,json={'full_name':'Asha Staff','role':'manager','phone':'9876543310'})
    assert created.status_code==201 and created.json()['role']=='manager'
    staff_id=created.json()['id']
    updated=client.patch(f'/api/provider/me/staff/{staff_id}',headers=h1,json={'role':'staff','is_active':False})
    assert updated.status_code==200 and updated.json()['is_active'] is False
    invalid=client.post('/api/provider/me/staff',headers=h1,json={'full_name':'Invalid','role':'admin'})
    assert invalid.status_code==400
    foreign=client.patch(f'/api/provider/me/staff/{staff_id}',headers=h2,json={'full_name':'Hijacked'})
    assert foreign.status_code==404
    assert len(client.get('/api/provider/me/staff',headers=h1).json())==1
    assert client.delete(f'/api/provider/me/staff/{staff_id}',headers=h1).status_code==200
    assert client.get('/api/provider/me/staff',headers=h1).json()==[]


def test_provider_branch_management_validation_and_owner_isolation():
    r1=client.post('/api/auth/register',json={'full_name':'Branch Owner One','email':'branch-owner-one@example.com','phone':'9876543311','password':'StrongPass123!','role':'provider'})
    r2=client.post('/api/auth/register',json={'full_name':'Branch Owner Two','email':'branch-owner-two@example.com','phone':'9876543312','password':'StrongPass123!','role':'provider'})
    h1={'Authorization':f"Bearer {r1.json()['access_token']}"};h2={'Authorization':f"Bearer {r2.json()['access_token']}"}
    for headers,name,city,loc in [(h1,'Branch Provider One','Coimbatore','Vadavalli'),(h2,'Branch Provider Two','Chennai','Adyar')]:
        assert client.post('/api/provider/register',headers=headers,json={'name':name,'category':'Salon','city':city,'locality':loc,'description':''}).status_code==201
    created=client.post('/api/provider/me/branches',headers=h1,json={'branch_name':'Downtown','city':'Coimbatore','locality':'RS Puram','address':'12 Main Road','phone':'9876543313'})
    assert created.status_code==201
    branch_id=created.json()['id']
    assert client.get('/api/provider/me/branches',headers=h1).json()[0]['branch_name']=='Downtown'
    updated=client.patch(f'/api/provider/me/branches/{branch_id}',headers=h1,json={'city':'Chennai','is_active':False})
    assert updated.status_code==200 and updated.json()['city']=='Chennai' and updated.json()['is_active'] is False
    invalid=client.post('/api/provider/me/branches',headers=h1,json={'branch_name':'Bad City','city':'Madurai','locality':'Central','address':'Road'})
    assert invalid.status_code==400
    foreign=client.delete(f'/api/provider/me/branches/{branch_id}',headers=h2)
    assert foreign.status_code==404
    assert client.delete(f'/api/provider/me/branches/{branch_id}',headers=h1).status_code==200
    assert client.get('/api/provider/me/branches',headers=h1).json()==[]


def test_concurrent_booking_requests_do_not_double_book_same_time():
    from concurrent.futures import ThreadPoolExecutor
    client.post('/api/admin/demo-seed')
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0]
    service=provider['services'][0]
    start=datetime.combine((datetime.now()+timedelta(days=20)).date(),datetime.strptime('11:00','%H:%M').time()).isoformat()
    payload={'customer_name':'Concurrent Customer','customer_phone':'9876543314','provider_id':provider['id'],'service_id':service['id'],'appointment_at':start,'notes':''}
    def submit():
        return client.post('/api/bookings',json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:submit(),range(2)))
    statuses=sorted(r.status_code for r in responses)
    assert statuses==[201,409], [r.status_code for r in responses]


def test_booking_rejects_non_slot_aligned_and_timezone_offset_times():
    client.post('/api/admin/demo-seed')
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0]
    service=provider['services'][0]
    day=(datetime.now()+timedelta(days=21)).date()
    base=datetime.combine(day,datetime.strptime('10:00','%H:%M').time())
    payload={'customer_name':'Slot Validation','customer_phone':'9876543315','provider_id':provider['id'],'service_id':service['id'],'appointment_at':(base+timedelta(minutes=5)).isoformat(),'notes':''}
    assert client.post('/api/bookings',json=payload).status_code==400
    payload['appointment_at']=base.isoformat()+'+05:30'
    assert client.post('/api/bookings',json=payload).status_code==400


def test_booking_reschedule_owner_validation_and_conflicts():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Reschedule Customer','email':'reschedule-customer@example.com','phone':'9876543316','password':'StrongPass123!','role':'customer'})
    other=client.post('/api/auth/register',json={'full_name':'Other Reschedule Customer','email':'reschedule-other@example.com','phone':'9876543317','password':'StrongPass123!','role':'customer'})
    h={'Authorization':f"Bearer {customer.json()['access_token']}"};ho={'Authorization':f"Bearer {other.json()['access_token']}"}
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0];service=provider['services'][0]
    day=(datetime.now()+timedelta(days=22)).date();first_time=datetime.combine(day,datetime.strptime('10:00','%H:%M').time());conflict_time=datetime.combine(day,datetime.strptime('11:00','%H:%M').time())
    b1=client.post('/api/bookings',headers=h,json={'customer_name':'Reschedule Customer','customer_phone':'9876543316','provider_id':provider['id'],'service_id':service['id'],'appointment_at':first_time.isoformat(),'notes':''})
    b2=client.post('/api/bookings',headers=ho,json={'customer_name':'Other Reschedule Customer','customer_phone':'9876543317','provider_id':provider['id'],'service_id':service['id'],'appointment_at':conflict_time.isoformat(),'notes':''})
    assert b1.status_code==201 and b2.status_code==201
    forbidden=client.patch(f"/api/bookings/{b1.json()['id']}/reschedule",headers=ho,json={'appointment_at':conflict_time.isoformat()})
    assert forbidden.status_code==403
    invalid=client.patch(f"/api/bookings/{b1.json()['id']}/reschedule",headers=h,json={'appointment_at':(conflict_time+timedelta(minutes=5)).isoformat()})
    assert invalid.status_code==400
    collision=client.patch(f"/api/bookings/{b1.json()['id']}/reschedule",headers=h,json={'appointment_at':conflict_time.isoformat()})
    assert collision.status_code==409
    valid_time=datetime.combine(day,datetime.strptime('12:00','%H:%M').time())
    valid=client.patch(f"/api/bookings/{b1.json()['id']}/reschedule",headers=h,json={'appointment_at':valid_time.isoformat()})
    assert valid.status_code==200 and valid.json()['appointment_at'].startswith(valid_time.isoformat())


def test_booking_request_expires_after_24_hours_and_is_rejected_on_status_change():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Expiry Customer','email':'expiry-customer@example.com','phone':'9876543318','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0];service=provider['services'][0]
    day=(datetime.now()+timedelta(days=23)).date();appointment=datetime.combine(day,datetime.strptime('10:00','%H:%M').time())
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Expiry Customer','customer_phone':'9876543318','provider_id':provider['id'],'service_id':service['id'],'appointment_at':appointment.isoformat(),'notes':''})
    assert booking.status_code==201
    with SessionLocal() as db:
        row=db.query(__import__('app.models',fromlist=['Booking']).Booking).filter_by(id=booking.json()['id']).first()
        row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    response=client.patch(f"/api/bookings/{booking.json()['id']}/status?status=confirmed",headers=headers)
    assert response.status_code==400 and 'expired' in response.json()['detail'].lower()
    with SessionLocal() as db:
        row=db.query(__import__('app.models',fromlist=['Booking']).Booking).filter_by(id=booking.json()['id']).first()
        assert row.status=='expired'


def test_customer_waitlist_create_list_duplicate_cancel_and_owner_scope():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Waitlist Customer','email':'waitlist-customer@example.com','phone':'9876543319','password':'StrongPass123!','role':'customer'})
    other=client.post('/api/auth/register',json={'full_name':'Waitlist Other','email':'waitlist-other@example.com','phone':'9876543320','password':'StrongPass123!','role':'customer'})
    h={'Authorization':f"Bearer {customer.json()['access_token']}"};ho={'Authorization':f"Bearer {other.json()['access_token']}"}
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0];service=provider['services'][0]
    preferred=datetime.combine((datetime.now()+timedelta(days=25)).date(),datetime.strptime('00:00','%H:%M').time())
    payload={'provider_id':provider['id'],'service_id':service['id'],'preferred_date':preferred.isoformat(),'preferred_time_start':'10:00','preferred_time_end':'13:00'}
    created=client.post('/api/customer/me/waitlist',headers=h,json=payload);assert created.status_code==201
    assert client.get('/api/customer/me/waitlist',headers=h).json()[0]['id']==created.json()['id']
    duplicate=client.post('/api/customer/me/waitlist',headers=h,json=payload);assert duplicate.status_code==409
    invalid_range={**payload,'preferred_time_start':'14:00','preferred_time_end':'13:00'}
    assert client.post('/api/customer/me/waitlist',headers=h,json=invalid_range).status_code==400
    stranger=client.delete(f"/api/customer/me/waitlist/{created.json()['id']}",headers=ho);assert stranger.status_code==404
    cancelled=client.delete(f"/api/customer/me/waitlist/{created.json()['id']}",headers=h);assert cancelled.status_code==200
    assert client.delete(f"/api/customer/me/waitlist/{created.json()['id']}",headers=h).status_code==400


def test_cancellation_policy_hook_and_provider_policy_validation():
    from app import models
    from app.database import get_db
    client.post('/api/admin/demo-seed')
    provider=client.get('/api/providers',params={'city':'Coimbatore','category':'Salon'}).json()[0];service=provider['services'][0]
    customer=client.post('/api/auth/register',json={'full_name':'Policy Customer','email':'policy-customer@example.com','phone':'9876543321','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    day=(datetime.now()+timedelta(days=2)).date();appointment=datetime.combine(day,datetime.strptime('10:00','%H:%M').time())
    payload={'customer_name':'Policy Customer','customer_phone':'9876543321','provider_id':provider['id'],'service_id':service['id'],'appointment_at':appointment.isoformat(),'notes':''}
    booking=client.post('/api/bookings',headers=headers,json=payload);assert booking.status_code==201
    db=next(get_db())
    try:
        p=db.query(models.Provider).filter(models.Provider.id==provider['id']).first()
        cfg=json.loads(p.availability_config or '{}');cfg['cancellation_min_hours']=48;cfg['cancellation_fee_percent']=20;p.availability_config=json.dumps(cfg);db.commit()
    finally:db.close()
    result=client.patch(f"/api/bookings/{booking.json()['id']}/status?status=cancelled",headers=headers)
    assert result.status_code==200 and result.json()['cancellation_policy']['fee_applies'] is True and result.json()['cancellation_policy']['fee_percent']==20


def test_provider_can_configure_cancellation_policy_with_bounds():
    reg=client.post('/api/auth/register',json={'full_name':'Cancel Policy Provider','email':'cancel-policy-provider@example.com','phone':'9876543322','password':'StrongPass123!','role':'provider'})
    h={'Authorization':f"Bearer {reg.json()['access_token']}"}
    listing=client.post('/api/provider/register',headers=h,json={'name':'Cancel Policy Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Policy test'});assert listing.status_code==201
    payload={'working_days':[0,1,2,3,4,5,6],'start_time':'09:00','end_time':'18:00','break_start':'','break_end':'','closed_dates':[],'cancellation_min_hours':24,'cancellation_fee_percent':25}
    valid=client.put('/api/provider/me/availability',headers=h,json=payload);assert valid.status_code==200 and valid.json()['cancellation_fee_percent']==25
    assert client.put('/api/provider/me/availability',headers=h,json={**payload,'cancellation_min_hours':169}).status_code==400
    assert client.put('/api/provider/me/availability',headers=h,json={**payload,'cancellation_fee_percent':101}).status_code==400


def test_full_and_advance_payment_amounts_and_invalid_type():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Advance Customer','email':'advance-customer@example.com','phone':'9876543323','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    provider=client.get('/api/providers').json()[0];service=provider['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=26)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Advance Customer','customer_phone':'9876543323','provider_id':provider['id'],'service_id':service['id'],'appointment_at':at,'notes':''});assert booking.status_code==201
    bid=booking.json()['id']
    invalid=client.post('/api/payments',headers={**headers,'Idempotency-Key':'test-idem-advanceinvalid0001'},json={'booking_id':bid,'payment_type':'other'});assert invalid.status_code==400
    advance=client.post('/api/payments',headers={**headers,'Idempotency-Key':'test-idem-advancevalid0001'},json={'booking_id':bid,'payment_type':'advance'});assert advance.status_code==201
    total=service['price_inr'];expected=max(1,(total*20+99)//100)
    assert advance.json()['amount_inr']==expected and advance.json()['balance_due_inr']==total-expected and advance.json()['payment_type']=='advance'
    assert advance.json()['gateway']=='unconfigured' and 'no money collected' in advance.json()['message'].lower()
    from app.models import User
    session=SessionLocal();admin=User(full_name='Finance Admin',email='finance-admin@example.com',phone='9876543326',password_hash=_password_hash('StrongPass123!'),role='admin',is_active=True);session.add(admin);session.commit();session.refresh(admin);admin_headers={'Authorization':f'Bearer {_make_token(admin.id)}'};session.close()
    ledger=client.get('/api/admin/payments',headers=admin_headers);assert ledger.status_code==200
    row=next(x for x in ledger.json()['payments'] if x['id']==advance.json()['id'])
    assert row['payment_type']=='advance' and row['balance_due_inr']==total-expected
    summary=client.get('/api/admin/payments/summary',headers=admin_headers);assert summary.status_code==200 and summary.json()['by_payment_type']['advance']['amount_inr']==expected


def test_admin_commission_rules_validation_and_permissions():
    from app.models import User
    session=SessionLocal();admin=User(full_name='Commission Admin',email='commission-admin@example.com',phone='9876543324',password_hash=_password_hash('StrongPass123!'),role='admin',is_active=True);session.add(admin);session.commit();session.refresh(admin);token=_make_token(admin.id);session.close()
    headers={'Authorization':f'Bearer {token}'}
    initial=client.get('/api/admin/commission-rules',headers=headers);assert initial.status_code==200 and len(initial.json())==4
    updated=client.put('/api/admin/commission-rules',headers=headers,json={'rules':[{'category':'Salon','commission_percent':10},{'category':'Makeup','commission_percent':8}]});assert updated.status_code==200
    assert next(r for r in updated.json() if r['category']=='Salon')['commission_percent']==10
    assert client.put('/api/admin/commission-rules',headers=headers,json={'rules':[{'category':'Salon','commission_percent':31}]}).status_code==400
    assert client.put('/api/admin/commission-rules',headers=headers,json={'rules':[{'category':'Unknown','commission_percent':5}]}).status_code==400
    customer=client.post('/api/auth/register',json={'full_name':'Commission Customer','email':'commission-customer@example.com','phone':'9876543325','password':'StrongPass123!','role':'customer'})
    customer_headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    assert client.get('/api/admin/commission-rules',headers=customer_headers).status_code==403


def test_staff_specific_booking_capacity_and_slot_filtering():
    owner=client.post('/api/auth/register',json={'full_name':'Staff Booking Owner','email':'staff-booking-owner@example.com','phone':'9876543327','password':'StrongPass123!','role':'provider'})
    headers={'Authorization':f"Bearer {owner.json()['access_token']}"}
    assert client.post('/api/provider/register',headers=headers,json={'name':'Staff Booking Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':''}).status_code==201
    staff_a=client.post('/api/provider/me/staff',headers=headers,json={'full_name':'Staff A','role':'staff','phone':'9876543328'}).json()
    staff_b=client.post('/api/provider/me/staff',headers=headers,json={'full_name':'Staff B','role':'staff','phone':'9876543329'}).json()
    provider=client.get('/api/provider/me',headers=headers).json()
    from app.models import Provider
    session=SessionLocal();row=session.query(Provider).filter_by(id=provider['id']).first();row.approval_status='approved';session.commit();session.close()
    service=client.post('/api/provider/me/services',headers=headers,params={'name':'Staff Booking Service','price_inr':1000,'duration_minutes':30});assert service.status_code==201;svc=service.json()
    at=datetime.combine((datetime.now()+timedelta(days=27)).date(),datetime.strptime('10:00','%H:%M').time())
    def payload(staff):return {'customer_name':'Staff Customer','customer_phone':'9876543330','provider_id':provider['id'],'service_id':svc['id'],'appointment_at':at.isoformat(),'staff_id':staff['id']}
    first=client.post('/api/bookings',json=payload(staff_a));assert first.status_code==201
    different=client.post('/api/bookings',json=payload(staff_b));assert different.status_code==201
    same=client.post('/api/bookings',json=payload(staff_a));assert same.status_code==409
    slots_a=client.get('/api/providers/'+str(provider['id'])+'/available-slots',params={'date':at.date().isoformat(),'service_id':svc['id'],'staff_id':staff_a['id']}).json()['slots']
    slots_b=client.get('/api/providers/'+str(provider['id'])+'/available-slots',params={'date':at.date().isoformat(),'service_id':svc['id'],'staff_id':staff_b['id']}).json()['slots']
    assert '10:00' not in slots_a and '10:00' not in slots_b


def test_razorpay_order_checkout_signature_and_webhook_dedup(monkeypatch):
    from app import payment_gateway
    monkeypatch.setenv('RAZORPAY_KEY_ID','rzp_test_fake_key');monkeypatch.setenv('RAZORPAY_KEY_SECRET','fake_secret');monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET','fake_webhook_secret')
    monkeypatch.setattr(payment_gateway,'create_order',lambda amount,receipt,notes:{'id':'order_mock_123','amount':amount*100,'currency':'INR','receipt':receipt})
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Gateway Customer','email':'gateway-customer@example.com','phone':'9876543331','password':'StrongPass123!','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    provider=client.get('/api/providers').json()[0];service=provider['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=28)).date(),datetime.strptime('10:00','%H:%M').time())
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Gateway Customer','customer_phone':'9876543331','provider_id':provider['id'],'service_id':service['id'],'appointment_at':at.isoformat(),'notes':''});assert booking.status_code==201
    created=client.post('/api/payments',headers={**headers,'Idempotency-Key':'test-idem-razorpaytestkey001'},json={'booking_id':booking.json()['id'],'payment_type':'full'});assert created.status_code==201
    d=created.json()['gateway_details'];assert d['order_id']=='order_mock_123' and d['key_id']=='rzp_test_fake_key' and created.json()['gateway']=='razorpay'
    payment_id=created.json()['id'];pay_id='pay_mock_456';sig=hmac.new(b'fake_secret',b'order_mock_123|pay_mock_456',hashlib.sha256).hexdigest()
    invalid=client.post(f'/api/payments/{payment_id}/verify',headers=headers,json={'razorpay_order_id':'order_mock_123','razorpay_payment_id':pay_id,'razorpay_signature':'bad'});assert invalid.status_code==400
    verified=client.post(f'/api/payments/{payment_id}/verify',headers=headers,json={'razorpay_order_id':'order_mock_123','razorpay_payment_id':pay_id,'razorpay_signature':sig});assert verified.status_code==200 and verified.json()['status']=='paid'
    body=json.dumps({'event':'payment.captured','payload':{'payment':{'entity':{'id':pay_id,'order_id':'order_mock_123','amount':service['price_inr']*100}}}},separators=(',',':')).encode()
    whsig=hmac.new(b'fake_webhook_secret',body,hashlib.sha256).hexdigest();whheaders={'X-Razorpay-Signature':whsig,'x-razorpay-event-id':'evt_mock_001'}
    first=client.post('/api/payments/razorpay/webhook',content=body,headers=whheaders);assert first.status_code==200 and first.json()['status']=='processed'
    duplicate=client.post('/api/payments/razorpay/webhook',content=body,headers=whheaders);assert duplicate.status_code==200 and duplicate.json()['duplicate'] is True
    tampered=client.post('/api/payments/razorpay/webhook',content=body+b' ',headers=whheaders);assert tampered.status_code==400
    record=client.get('/api/payments/me',headers=headers).json()[0];assert record['status']=='paid' and record['gateway_payment_id']==pay_id


def test_otp_expired_challenge_is_rejected():
    import app.main as main_module
    from app.models import OTPChallenge
    from datetime import datetime, timedelta
    request = client.post('/api/v2/customer/otp/request', json={'phone':'9876543350'})
    assert request.status_code == 200
    challenge = request.json()['development_otp']
    db = SessionLocal()
    try:
        row = db.query(OTPChallenge).filter_by(phone='+919876543350').order_by(OTPChallenge.created_at.desc()).first()
        assert row is not None
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    response = client.post('/api/v2/customer/otp/verify', json={'phone':'9876543350','otp':challenge})
    assert response.status_code == 401
    assert 'expired' in response.text.lower()


def test_otp_challenge_cannot_be_replayed():
    request = client.post('/api/v2/customer/otp/request', json={'phone':'9876543351'})
    assert request.status_code == 200
    otp = request.json()['development_otp']
    first = client.post('/api/v2/customer/otp/verify', json={'phone':'9876543351','otp':otp})
    assert first.status_code == 200
    second = client.post('/api/v2/customer/otp/verify', json={'phone':'9876543351','otp':otp})
    assert second.status_code == 401


def test_customer_otp_request_is_disabled_when_development_mode_is_off(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, 'OTP_DEV_MODE', False)
    response = client.post('/api/v2/customer/otp/request', json={'phone':'9876543352'})
    assert response.status_code == 503
    assert 'SMS OTP delivery is not configured' in response.text


def test_production_requires_private_portfolio_storage(monkeypatch, tmp_path):
    import app.main as main_module
    import app.database as database_module
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main_module,'AUTH_SECRET',b'a'*40)
    monkeypatch.setattr(main_module,'OTP_DEV_MODE',False)
    monkeypatch.setattr(main_module,'_CORS_ORIGINS',['https://lushora.example'])
    monkeypatch.setattr(database_module,'DATABASE_URL','postgresql://user:password@db.example/lushora')
    verification=tmp_path/'verification';verification.mkdir(mode=0o700)
    backup=tmp_path/'backup';backup.mkdir(mode=0o700)
    monkeypatch.setenv('LUSHORA_VERIFICATION_UPLOAD_DIR',str(verification))
    monkeypatch.setenv('LUSHORA_BACKUP_DIR',str(backup))
    monkeypatch.setenv('LUSHORA_BACKUP_RETENTION_DAYS','7')
    monkeypatch.delenv('LUSHORA_PORTFOLIO_UPLOAD_DIR',raising=False)
    with pytest.raises(RuntimeError,match='LUSHORA_PORTFOLIO_UPLOAD_DIR'):
        main_module._validate_production_settings()


def test_production_rejects_repo_local_portfolio_storage(monkeypatch, tmp_path):
    import app.main as main_module
    import app.database as database_module
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setattr(main_module,'AUTH_SECRET',b'a'*40)
    monkeypatch.setattr(main_module,'OTP_DEV_MODE',False)
    monkeypatch.setattr(main_module,'_CORS_ORIGINS',['https://lushora.example'])
    monkeypatch.setattr(database_module,'DATABASE_URL','postgresql://user:password@db.example/lushora')
    verification=tmp_path/'verification';verification.mkdir(mode=0o700)
    backup=tmp_path/'backup';backup.mkdir(mode=0o700)
    monkeypatch.setenv('LUSHORA_VERIFICATION_UPLOAD_DIR',str(verification))
    monkeypatch.setenv('LUSHORA_BACKUP_DIR',str(backup))
    monkeypatch.setenv('LUSHORA_BACKUP_RETENTION_DAYS','7')
    repo_portfolio=main_module.Path(__file__).resolve().parents[2]/'portfolio_uploads'
    monkeypatch.setenv('LUSHORA_PORTFOLIO_UPLOAD_DIR',str(repo_portfolio))
    with pytest.raises(RuntimeError,match='application repository'):
        main_module._validate_production_settings()


def test_otp_audit_events_hash_phone_and_ip_and_never_store_otp():
    from app.models import SecurityAuditEvent
    phone = '9876543353'
    request = client.post('/api/v2/customer/otp/request', json={'phone': phone})
    assert request.status_code == 200
    otp = request.json()['development_otp']
    verify = client.post('/api/v2/customer/otp/verify', json={'phone': phone, 'otp': otp})
    assert verify.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(SecurityAuditEvent).filter(
            SecurityAuditEvent.event_type.in_(['otp_requested', 'otp_verify_success'])
        ).order_by(SecurityAuditEvent.created_at.asc()).all()
        assert {event.event_type for event in events} >= {'otp_requested', 'otp_verify_success'}
        expected_phone_hash = __import__('app.main', fromlist=['_rate_limit_identifier'])._rate_limit_identifier('+91' + phone)
        expected_ip_hash = __import__('app.main', fromlist=['_rate_limit_identifier'])._rate_limit_identifier('127.0.0.1')
        for event in events:
            assert event.identifier_hash == expected_phone_hash
            assert event.ip_hash == expected_ip_hash
            assert phone not in event.identifier_hash
            assert otp not in event.identifier_hash
            assert otp not in event.ip_hash
    finally:
        db.close()
