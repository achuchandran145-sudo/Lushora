from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

client = TestClient(app)

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

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
    payload={'customer_name':'Test Customer','customer_phone':'9876543210','provider_id':p['id'],'service_id':service['id'],'appointment_at':(datetime.now()+timedelta(days=2)).isoformat(),'notes':'Test'}
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
    start = datetime.now() + timedelta(days=3)
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
    overlap['appointment_at'] = (start + timedelta(minutes=5)).isoformat()
    assert client.post('/api/bookings', json=overlap).status_code == 409
    non_overlap = payload.copy()
    non_overlap['customer_name'] = 'Third Customer'
    non_overlap['appointment_at'] = (start + timedelta(minutes=service['duration_minutes'] + 5)).isoformat()
    assert client.post('/api/bookings', json=non_overlap).status_code == 201


def test_customer_register_login_and_me():
    registration = client.post('/api/auth/register', json={'full_name':'Test User','email':'test-user@example.com','phone':'9876543210','password':'StrongPass123','role':'customer'})
    assert registration.status_code == 201
    token = registration.json()['access_token']
    profile = client.get('/api/auth/me', headers={'Authorization':f'Bearer {token}'})
    assert profile.status_code == 200
    assert profile.json()['role'] == 'customer'
    login = client.post('/api/auth/login', json={'email':'test-user@example.com','password':'StrongPass123'})
    assert login.status_code == 200
    assert client.post('/api/auth/login', json={'email':'test-user@example.com','password':'wrongpass'}).status_code == 401


def test_provider_registration_is_pending():
    registration = client.post('/api/auth/register', json={'full_name':'Provider User','email':'provider-user@example.com','phone':'9876543211','password':'StrongPass123','role':'provider'})
    assert registration.status_code == 201
    token = registration.json()['access_token']
    submission = client.post('/api/provider/register', headers={'Authorization':f'Bearer {token}'}, json={'name':'New Studio','category':'Salon','city':'Coimbatore','locality':'Vadavalli','description':'Test business'})
    assert submission.status_code == 201
    assert submission.json()['approval_status'] == 'pending'
    assert len(client.get('/api/providers').json()) == 0

def test_notification_preferences_default_external_channels_off():
    registration=client.post('/api/auth/register',json={'full_name':'Notify User','email':'notify-default@example.com','phone':'9876543212','password':'StrongPass123','role':'customer'})
    token=registration.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    prefs=client.get('/api/me/notification-preferences',headers=headers)
    assert prefs.status_code==200
    assert prefs.json()=={'in_app_enabled':True,'push_enabled':False,'whatsapp_enabled':False,'sms_enabled':False}

def test_notification_preferences_validate_and_opt_in_opt_out():
    registration=client.post('/api/auth/register',json={'full_name':'Notify User','email':'notify-opt@example.com','phone':'9876543213','password':'StrongPass123','role':'customer'})
    token=registration.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    invalid=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':'yes'})
    assert invalid.status_code==400
    opted=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':True,'whatsapp_enabled':True})
    assert opted.status_code==200 and opted.json()['sms_enabled'] is True and opted.json()['whatsapp_enabled'] is True
    opted_out=client.put('/api/me/notification-preferences',headers=headers,json={'sms_enabled':False})
    assert opted_out.status_code==200 and opted_out.json()['sms_enabled'] is False and opted_out.json()['whatsapp_enabled'] is True

def test_provider_owner_can_register_multiple_categories_but_not_duplicate_category():
    registration = client.post('/api/auth/register', json={'full_name':'Multi Category Provider','email':'multi-provider@example.com','phone':'9876543220','password':'StrongPass123','role':'provider'})
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
    registration = client.post('/api/auth/register', json={'full_name':'Profile Test','email':'profile-test@example.com','phone':'9876543230','password':'StrongPass123','role':'customer'})
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
    provider_reg = client.post('/api/auth/register',json={'full_name':'Availability Provider','email':'availability-provider@example.com','phone':'9876543231','password':'StrongPass123','role':'provider'})
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
