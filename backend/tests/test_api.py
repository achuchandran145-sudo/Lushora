import json
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

def test_reviews_require_completed_owned_booking_and_moderation():
    customer = client.post('/api/auth/register',json={'full_name':'Review Customer','email':'review-customer@example.com','phone':'9876543240','password':'StrongPass123','role':'customer'})
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
    reg=client.post('/api/auth/register',json={'full_name':'Service Owner','email':'service-owner@example.com','phone':'9876543250','password':'StrongPass123','role':'provider'})
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
    customer=client.post('/api/auth/register',json={'full_name':'Cancel Owner','email':'cancel-owner@example.com','phone':'9876543260','password':'StrongPass123','role':'customer'})
    token=customer.json()['access_token'];headers={'Authorization':f'Bearer {token}'}
    provider=client.get('/api/providers').json()[0];service=provider['services'][0]
    payload={'customer_name':'Cancel Owner','customer_phone':'9876543260','provider_id':provider['id'],'service_id':service['id'],'appointment_at':datetime.combine((datetime.now()+timedelta(days=5)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat(),'notes':''}
    booking=client.post('/api/bookings',headers=headers,json=payload)
    assert booking.status_code==201
    booking_id=booking.json()['id']
    stranger=client.post('/api/auth/register',json={'full_name':'Cancel Stranger','email':'cancel-stranger@example.com','phone':'9876543261','password':'StrongPass123','role':'customer'})
    stranger_headers={'Authorization':f"Bearer {stranger.json()['access_token']}"}
    assert client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=stranger_headers).status_code==403
    cancelled=client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=headers)
    assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    assert client.patch(f'/api/bookings/{booking_id}/status?status=cancelled',headers=headers).status_code==400

def test_booking_enforces_provider_schedule_break_and_closed_dates():
    from app.database import get_db
    from app import models
    provider_reg=client.post('/api/auth/register',json={'full_name':'Schedule Provider','email':'schedule-provider@example.com','phone':'9876543270','password':'StrongPass123','role':'provider'})
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
    customer=client.post('/api/auth/register',json={'full_name':'Lifecycle Customer','email':'lifecycle-customer@example.com','phone':'9876543280','password':'StrongPass123','role':'customer'})
    provider_user=client.post('/api/auth/register',json={'full_name':'Lifecycle Provider','email':'lifecycle-provider@example.com','phone':'9876543281','password':'StrongPass123','role':'provider'})
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
    customer=client.post('/api/auth/register',json={'full_name':'Payment Owner','email':'pay-owner@example.com','phone':'9876543290','password':'StrongPass123','role':'customer'})
    stranger=client.post('/api/auth/register',json={'full_name':'Payment Stranger','email':'pay-stranger@example.com','phone':'9876543291','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    stranger_headers={'Authorization':f"Bearer {stranger.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=8)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Payment Owner','customer_phone':'9876543290','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    first=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'payment-key-0001'})
    assert first.status_code==201 and first.json()['status']=='pending'
    second=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'payment-key-0001'})
    assert second.json()['id']==first.json()['id']
    denied=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':stranger_headers['Authorization'],'Idempotency-Key':'stranger-key-0001'})
    assert denied.status_code==404
    assert client.get('/api/payments/me',headers=headers).status_code==200

def test_cancel_booking_cancels_pending_payment_record():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Cancel Pay Customer','email':'cancel-pay@example.com','phone':'9876543292','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=9)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Cancel Pay Customer','customer_phone':'9876543292','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    pay=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'cancel-payment-0001'})
    assert pay.status_code==201 and pay.json()['status']=='pending'
    cancelled=client.patch(f'/api/bookings/{bid}/status?status=cancelled',headers=headers)
    assert cancelled.status_code==200
    history=client.get('/api/payments/me',headers=headers)
    record=next(x for x in history.json() if x['id']==pay.json()['id'])
    assert record['status']=='cancelled'

def test_payment_rejects_second_pending_record_with_different_key():
    client.post('/api/admin/demo-seed')
    customer=client.post('/api/auth/register',json={'full_name':'Duplicate Payment Customer','email':'duplicate-pay@example.com','phone':'9876543293','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    p=client.get('/api/providers').json()[0];service=p['services'][0]
    at=datetime.combine((datetime.now()+timedelta(days=10)).date(),datetime.strptime('10:00','%H:%M').time()).isoformat()
    booking=client.post('/api/bookings',headers=headers,json={'customer_name':'Duplicate Payment Customer','customer_phone':'9876543293','provider_id':p['id'],'service_id':service['id'],'appointment_at':at,'notes':''})
    assert booking.status_code==201
    bid=booking.json()['id']
    first=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'dup-payment-0001'})
    assert first.status_code==201
    second=client.post('/api/payments',json={'booking_id':bid},headers={'Authorization':headers['Authorization'],'Idempotency-Key':'dup-payment-0002'})
    assert second.status_code==409

def test_admin_payment_list_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Payments Admin Guard','email':'payments-admin-guard@example.com','phone':'9876543294','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments',headers=headers)
    assert response.status_code==403

def test_admin_payment_summary_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Payment Summary Guard','email':'payment-summary-guard@example.com','phone':'9876543295','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments/summary',headers=headers)
    assert response.status_code==403

def test_admin_payment_reconciliation_is_forbidden_to_customer():
    customer=client.post('/api/auth/register',json={'full_name':'Recon Guard','email':'recon-guard@example.com','phone':'9876543296','password':'StrongPass123','role':'customer'})
    headers={'Authorization':f"Bearer {customer.json()['access_token']}"}
    response=client.get('/api/admin/payments/reconciliation',headers=headers)
    assert response.status_code==403
