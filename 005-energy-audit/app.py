import json
import os
import math
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///energy_audit.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'mvp-seed-data.json')
with open(SEED_DATA_PATH) as f:
    SEED_DATA = json.load(f)

CHECKLIST_ITEMS = SEED_DATA['checklistTemplate']['items']
COMPLIANCE_RULES = {r['metricType']: r for r in SEED_DATA['complianceRules']}
CONSTANTS = SEED_DATA['constants']
BD_CAL = CONSTANTS['blowerDoorCalibration']
DB_CAL = CONSTANTS['ductBlasterCalibration']


def now_utc():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    state = db.Column(db.String(255), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    builder_name = db.Column(db.String(255), nullable=False)
    scheduled_date = db.Column(db.Date, nullable=False)
    house_volume = db.Column(db.Float, nullable=False)
    conditioned_floor_area = db.Column(db.Float, nullable=False)
    num_stories = db.Column(db.Float, nullable=True)
    surface_area = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=now_utc)

    checklist_items = db.relationship('ChecklistItem', backref='job', lazy=True, cascade='all, delete-orphan')
    blower_door_points = db.relationship('BlowerDoorPoint', backref='job', lazy=True, cascade='all, delete-orphan')
    blower_door_result = db.relationship('BlowerDoorResult', backref='job', lazy=True, cascade='all, delete-orphan', uselist=False)
    duct_leakage = db.relationship('DuctLeakage', backref='job', lazy=True, cascade='all, delete-orphan', uselist=False)
    photos = db.relationship('Photo', backref='job', lazy=True, cascade='all, delete-orphan')

    def to_summary_dict(self):
        addr = f"{self.street}, {self.city}, {self.state} {self.zip_code}"
        return {
            'id': self.id,
            'address': addr,
            'builder': self.builder_name,
            'scheduled_date': self.scheduled_date.isoformat() if self.scheduled_date else None,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def to_detail_dict(self):
        return {
            'id': self.id,
            'address': {
                'street': self.street,
                'city': self.city,
                'state': self.state,
                'zip': self.zip_code
            },
            'builder_name': self.builder_name,
            'scheduled_date': self.scheduled_date.isoformat() if self.scheduled_date else None,
            'house_volume': self.house_volume,
            'conditioned_floor_area': self.conditioned_floor_area,
            'num_stories': self.num_stories,
            'surface_area': self.surface_area,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ChecklistItem(db.Model):
    __tablename__ = 'checklist_items'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    item_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='Not Started')

    def to_dict(self):
        return {
            'item_number': self.item_number,
            'title': self.title,
            'status': self.status
        }


class BlowerDoorPoint(db.Model):
    __tablename__ = 'blower_door_points'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    house_pressure = db.Column(db.Float, nullable=False)
    fan_pressure = db.Column(db.Float, nullable=False)
    ring_config = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'house_pressure': self.house_pressure,
            'fan_pressure': self.fan_pressure,
            'ring_config': self.ring_config
        }


class BlowerDoorResult(db.Model):
    __tablename__ = 'blower_door_results'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), unique=True, nullable=False)
    cfm50 = db.Column(db.Float, nullable=True)
    ach50 = db.Column(db.Float, nullable=True)
    n_factor = db.Column(db.Float, nullable=True)
    r_squared = db.Column(db.Float, nullable=True)
    warnings = db.Column(db.Text, nullable=True)
    calculated_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'cfm50': self.cfm50,
            'ach50': self.ach50,
            'n_factor': self.n_factor,
            'r_squared': self.r_squared,
            'warnings': json.loads(self.warnings) if self.warnings else [],
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None
        }


class DuctLeakage(db.Model):
    __tablename__ = 'duct_leakage'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), unique=True, nullable=False)
    test_type_selected = db.Column(db.String(50), nullable=False)
    tdl_ring_config = db.Column(db.String(50), nullable=True)
    tdl_fan_pressure = db.Column(db.Float, nullable=True)
    tdl_cfm25 = db.Column(db.Float, nullable=True)
    tdl_cfm25_per100 = db.Column(db.Float, nullable=True)
    tdl_compliance = db.Column(db.String(50), nullable=True)
    dlo_house_pressure = db.Column(db.Float, nullable=True)
    dlo_ring_config = db.Column(db.String(50), nullable=True)
    dlo_fan_pressure = db.Column(db.Float, nullable=True)
    dlo_cfm25 = db.Column(db.Float, nullable=True)
    dlo_cfm25_per100 = db.Column(db.Float, nullable=True)
    dlo_compliance = db.Column(db.String(50), nullable=True)
    dlo_house_pressure_warning = db.Column(db.String(500), nullable=True)
    overall_compliance = db.Column(db.String(50), nullable=True)
    calculated_at = db.Column(db.DateTime, nullable=True)

    def tdl_dict(self):
        if self.tdl_cfm25 is None:
            return None
        return {
            'ring_config': self.tdl_ring_config,
            'fan_pressure': self.tdl_fan_pressure,
            'cfm25': self.tdl_cfm25,
            'cfm25_per100_sqft': self.tdl_cfm25_per100,
            'compliance': self.tdl_compliance
        }

    def dlo_dict(self):
        if self.dlo_cfm25 is None:
            return None
        return {
            'house_pressure': self.dlo_house_pressure,
            'ring_config': self.dlo_ring_config,
            'fan_pressure': self.dlo_fan_pressure,
            'cfm25': self.dlo_cfm25,
            'cfm25_per100_sqft': self.dlo_cfm25_per100,
            'compliance': self.dlo_compliance,
            'warning': self.dlo_house_pressure_warning
        }

    def to_dict(self):
        return {
            'test_type_selected': self.test_type_selected,
            'tdl': self.tdl_dict(),
            'dlo': self.dlo_dict(),
            'overall_compliance': self.overall_compliance,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None
        }


class Photo(db.Model):
    __tablename__ = 'photos'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'content_type': self.content_type,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def normalize_ring_config(ring_config):
    rc = str(ring_config).strip().lower().replace(' ', '').replace('-', '')
    mapping = {
        'open': 'openRing',
        'ringa': 'ringA',
        'ringb': 'ringB',
        'ringc': 'ringC',
        'ringd': 'ringD',
    }
    return mapping.get(rc)


def get_calibration_c_n(ring_config, calibration):
    key = normalize_ring_config(ring_config)
    if not key:
        return None, None
    entry = calibration.get(key)
    if not entry:
        return None, None
    return entry['C'], entry['n']


def compute_log_log_regression(points):
    x = [math.log(p[0]) for p in points]
    y = [math.log(p[1]) for p in points]
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    ss_xx = sum((xi - mean_x) ** 2 for xi in x)
    if ss_xx == 0:
        return None, None, None
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    ss_res = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    if ss_tot == 0:
        r_squared = 1.0
    else:
        r_squared = 1 - ss_res / ss_tot
    cfm50 = math.exp(intercept + slope * math.log(50))
    return cfm50, slope, r_squared


def update_job_status(job):
    items = ChecklistItem.query.filter_by(job_id=job.id).all()
    checklist_complete = all(item.status != 'Not Started' for item in items)

    points = BlowerDoorPoint.query.filter_by(job_id=job.id).all()
    result = BlowerDoorResult.query.filter_by(job_id=job.id).first()
    bd_complete = len(points) >= 5 and result is not None and result.calculated_at is not None

    dl = DuctLeakage.query.filter_by(job_id=job.id).first()
    dl_complete = False
    if dl is not None and dl.calculated_at is not None:
        if dl.tdl_cfm25 is not None or dl.dlo_cfm25 is not None:
            dl_complete = True

    if checklist_complete and bd_complete and dl_complete:
        job.status = 'Completed'
    elif checklist_complete or bd_complete or dl_complete:
        job.status = 'In Progress'
    else:
        job.status = 'Pending'


# Auth endpoints
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    if not name or not email or not password:
        return jsonify({'error': 'Missing required fields'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409
    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()
    session['user_id'] = user.id
    return jsonify(user.to_dict()), 201


@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = user.id
    return jsonify(user.to_dict()), 200


@app.route('/auth/logout', methods=['POST'])
@require_login
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'}), 200


@app.route('/auth/me', methods=['GET'])
@require_login
def me():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict()), 200


# Job endpoints
@app.route('/jobs', methods=['POST'])
@require_login
def create_job():
    data = request.get_json(silent=True) or {}
    required = ['address', 'builder_name', 'scheduled_date', 'house_volume', 'conditioned_floor_area']
    for key in required:
        if key not in data:
            return jsonify({'error': f'Missing required field: {key}'}), 400
    addr = data['address']
    for akey in ['street', 'city', 'state', 'zip']:
        if akey not in addr:
            return jsonify({'error': f'Missing address field: {akey}'}), 400
    try:
        sched = datetime.strptime(data['scheduled_date'], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid scheduled_date format, expected YYYY-MM-DD'}), 400

    job = Job(
        user_id=session['user_id'],
        street=str(addr['street']),
        city=str(addr['city']),
        state=str(addr['state']),
        zip_code=str(addr['zip']),
        builder_name=str(data['builder_name']),
        scheduled_date=sched,
        house_volume=float(data['house_volume']),
        conditioned_floor_area=float(data['conditioned_floor_area']),
        num_stories=float(data['num_stories']) if data.get('num_stories') is not None else None,
        surface_area=float(data['surface_area']) if data.get('surface_area') is not None else None,
        status='Pending'
    )
    db.session.add(job)
    db.session.flush()
    for item in CHECKLIST_ITEMS:
        ci = ChecklistItem(
            job_id=job.id,
            item_number=item['itemNumber'],
            title=item['title'],
            status='Not Started'
        )
        db.session.add(ci)
    db.session.commit()
    return jsonify(job.to_detail_dict()), 201


@app.route('/jobs', methods=['GET'])
@require_login
def list_jobs():
    jobs = Job.query.filter_by(user_id=session['user_id']).order_by(Job.created_at.desc()).all()
    return jsonify([job.to_summary_dict() for job in jobs])


@app.route('/jobs/<int:job_id>', methods=['GET'])
@require_login
def get_job(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    detail = job.to_detail_dict()

    items = ChecklistItem.query.filter_by(job_id=job.id).order_by(ChecklistItem.item_number).all()
    applicable = [i for i in items if i.status != 'N/A']
    passed_count = sum(1 for i in applicable if i.status == 'Passed')
    total_applicable = len(applicable)
    if total_applicable == 0:
        pass_rate = 0
    else:
        pass_rate = int(math.floor((passed_count / total_applicable) * 100 + 0.5))
    checklist_summary = f"{passed_count}/{total_applicable} Passed ({pass_rate}%)"

    detail['checklist'] = {
        'items': [i.to_dict() for i in items],
        'summary': checklist_summary,
        'complete': all(i.status != 'Not Started' for i in items)
    }

    points = BlowerDoorPoint.query.filter_by(job_id=job.id).all()
    result = BlowerDoorResult.query.filter_by(job_id=job.id).first()
    bd_complete = len(points) >= 5 and result is not None and result.calculated_at is not None
    detail['blower_door'] = {
        'points': [p.to_dict() for p in points],
        'result': result.to_dict() if result else None,
        'complete': bd_complete
    }

    dl = DuctLeakage.query.filter_by(job_id=job.id).first()
    dl_complete = False
    if dl is not None and dl.calculated_at is not None:
        if dl.tdl_cfm25 is not None or dl.dlo_cfm25 is not None:
            dl_complete = True
    detail['duct_leakage'] = {
        'config': dl.to_dict() if dl else None,
        'complete': dl_complete
    }

    photos = Photo.query.filter_by(job_id=job.id).all()
    detail['photos'] = {
        'photos': [p.to_dict() for p in photos],
        'count': len(photos),
        'complete': True
    }

    return jsonify(detail)


@app.route('/jobs/<int:job_id>/checklist', methods=['PUT'])
@require_login
def update_checklist(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    data = request.get_json(silent=True) or {}
    updates = data.get('items', [])
    for upd in updates:
        item_number = upd.get('item_number')
        new_status = upd.get('status')
        if new_status not in ('Not Started', 'Passed', 'Failed', 'N/A'):
            return jsonify({'error': 'Invalid status'}), 400
        item = ChecklistItem.query.filter_by(job_id=job.id, item_number=item_number).first()
        if item:
            item.status = new_status
    db.session.commit()
    update_job_status(job)
    db.session.commit()
    return jsonify({'message': 'Checklist updated'}), 200


@app.route('/jobs/<int:job_id>/blower-door/points', methods=['POST'])
@require_login
def add_blower_door_points(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    data = request.get_json(silent=True) or {}
    points_data = data.get('points', [])
    added = []
    for p in points_data:
        hp = float(p['house_pressure'])
        fp = float(p['fan_pressure'])
        rc = p['ring_config']
        point = BlowerDoorPoint(
            job_id=job.id,
            house_pressure=hp,
            fan_pressure=fp,
            ring_config=rc
        )
        db.session.add(point)
        added.append(point)
    db.session.commit()
    update_job_status(job)
    db.session.commit()
    return jsonify({'added': [ap.to_dict() for ap in added]}), 201


@app.route('/jobs/<int:job_id>/blower-door/calculate', methods=['POST'])
@require_login
def calculate_blower_door(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    points = BlowerDoorPoint.query.filter_by(job_id=job.id).all()
    if len(points) < CONSTANTS['minBlowerDoorTestPoints']:
        return jsonify({'error': f'At least {CONSTANTS["minBlowerDoorTestPoints"]} points required'}), 400

    pairs = []
    for p in points:
        c, n = get_calibration_c_n(p.ring_config, BD_CAL)
        if c is None:
            return jsonify({'error': f'Invalid ring configuration: {p.ring_config}'}), 400
        if p.fan_pressure <= 0 or p.house_pressure <= 0:
            return jsonify({'error': 'Pressures must be positive'}), 400
        cfm = c * (p.fan_pressure ** n)
        pairs.append((p.house_pressure, cfm))

    pairs.sort(key=lambda x: x[0])
    cfm50, n_factor, r_squared = compute_log_log_regression(pairs)
    if cfm50 is None:
        return jsonify({'error': 'Regression failed'}), 400
    ach50 = (cfm50 * 60) / job.house_volume
    warnings = []
    if r_squared < CONSTANTS['minCorrelationCoefficient']:
        warnings.append('Warning: Correlation is low (R² < 0.98).')

    result = BlowerDoorResult.query.filter_by(job_id=job.id).first()
    if not result:
        result = BlowerDoorResult(job_id=job.id)
        db.session.add(result)
    result.cfm50 = cfm50
    result.ach50 = ach50
    result.n_factor = n_factor
    result.r_squared = r_squared
    result.warnings = json.dumps(warnings)
    result.calculated_at = now_utc()
    db.session.commit()
    update_job_status(job)
    db.session.commit()
    return jsonify({
        'cfm50': cfm50,
        'ach50': ach50,
        'n_factor': n_factor,
        'r_squared': r_squared,
        'warnings': warnings,
        'compliance': 'Pass' if ach50 <= COMPLIANCE_RULES['ACH50']['threshold'] else 'Fail'
    }), 200


@app.route('/jobs/<int:job_id>/duct-leakage', methods=['POST'])
@require_login
def create_duct_leakage(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    data = request.get_json(silent=True) or {}
    test_type = data.get('test_type_selected')
    if test_type not in ('TDL only', 'DLO only', 'Both'):
        return jsonify({'error': 'Invalid test_type_selected'}), 400
    dl = DuctLeakage.query.filter_by(job_id=job.id).first()
    if not dl:
        dl = DuctLeakage(job_id=job.id, test_type_selected=test_type)
        db.session.add(dl)
    else:
        dl.test_type_selected = test_type
    db.session.commit()
    update_job_status(job)
    db.session.commit()
    return jsonify({'message': 'Duct leakage configuration set'}), 200


@app.route('/jobs/<int:job_id>/duct-leakage/calculate', methods=['POST'])
@require_login
def calculate_duct_leakage(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    dl = DuctLeakage.query.filter_by(job_id=job.id).first_or_404()
    data = request.get_json(silent=True) or {}

    warnings = []
    tdl_pass = None
    dlo_pass = None

    if dl.test_type_selected in ('TDL only', 'Both'):
        tdl_data = data.get('tdl', {})
        ring = tdl_data.get('ring_config')
        fan_pressure = float(tdl_data.get('fan_pressure'))
        c, n = get_calibration_c_n(ring, DB_CAL)
        if c is None:
            return jsonify({'error': f'Invalid TDL ring configuration: {ring}'}), 400
        if fan_pressure <= 0:
            return jsonify({'error': 'Fan pressure must be positive'}), 400
        cfm25 = c * (fan_pressure ** n)
        cfm25_per100 = (cfm25 * 100) / job.conditioned_floor_area
        tdl_pass = cfm25_per100 <= COMPLIANCE_RULES['TDL']['threshold']
        dl.tdl_ring_config = ring
        dl.tdl_fan_pressure = fan_pressure
        dl.tdl_cfm25 = cfm25
        dl.tdl_cfm25_per100 = cfm25_per100
        dl.tdl_compliance = 'Pass' if tdl_pass else 'Fail'

    if dl.test_type_selected in ('DLO only', 'Both'):
        dlo_data = data.get('dlo', {})
        house_pressure = float(dlo_data.get('house_pressure'))
        ring = dlo_data.get('ring_config')
        fan_pressure = float(dlo_data.get('fan_pressure'))
        c, n = get_calibration_c_n(ring, DB_CAL)
        if c is None:
            return jsonify({'error': f'Invalid DLO ring configuration: {ring}'}), 400
        if fan_pressure <= 0:
            return jsonify({'error': 'Fan pressure must be positive'}), 400
        cfm25 = c * (fan_pressure ** n)
        cfm25_per100 = (cfm25 * 100) / job.conditioned_floor_area
        dlo_pass = cfm25_per100 <= COMPLIANCE_RULES['DLO']['threshold']
        dl.dlo_house_pressure = house_pressure
        dl.dlo_ring_config = ring
        dl.dlo_fan_pressure = fan_pressure
        dl.dlo_cfm25 = cfm25
        dl.dlo_cfm25_per100 = cfm25_per100
        dl.dlo_compliance = 'Pass' if dlo_pass else 'Fail'
        if not (-27 <= house_pressure <= -23):
            warning_msg = 'Warning: House pressure outside -23 to -27 Pa range.'
            warnings.append(warning_msg)
            dl.dlo_house_pressure_warning = warning_msg
        else:
            dl.dlo_house_pressure_warning = None

    selected_results = []
    if dl.test_type_selected in ('TDL only', 'Both') and tdl_pass is not None:
        selected_results.append(tdl_pass)
    if dl.test_type_selected in ('DLO only', 'Both') and dlo_pass is not None:
        selected_results.append(dlo_pass)
    overall = all(selected_results) if selected_results else False
    dl.overall_compliance = 'Pass' if overall else 'Fail'
    dl.calculated_at = now_utc()
    db.session.commit()
    update_job_status(job)
    db.session.commit()

    resp = {
        'overall_compliance': dl.overall_compliance,
        'warnings': warnings
    }
    tdl_out = dl.tdl_dict()
    dlo_out = dl.dlo_dict()
    if tdl_out:
        resp['tdl'] = tdl_out
    if dlo_out:
        resp['dlo'] = dlo_out
    return jsonify(resp)


@app.route('/jobs/<int:job_id>/photos', methods=['POST'])
@require_login
def upload_photo(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    if Photo.query.filter_by(job_id=job.id).count() >= 10:
        return jsonify({'error': 'Maximum 10 photos reached'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    allowed = {'image/jpeg', 'image/png', 'image/webp'}
    ct = file.content_type
    if ct not in allowed:
        return jsonify({'error': 'Invalid file type. Only JPEG, PNG, WebP allowed.'}), 400
    photo = Photo(
        job_id=job.id,
        filename=file.filename,
        content_type=ct,
        data=file.read()
    )
    db.session.add(photo)
    db.session.commit()
    return jsonify(photo.to_dict()), 201


@app.route('/jobs/<int:job_id>/photos', methods=['GET'])
@require_login
def list_photos(job_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    photos = Photo.query.filter_by(job_id=job.id).all()
    return jsonify([p.to_dict() for p in photos])


@app.route('/jobs/<int:job_id>/photos/<int:photo_id>', methods=['GET'])
@require_login
def get_photo(job_id, photo_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    photo = Photo.query.filter_by(id=photo_id, job_id=job.id).first_or_404()
    return Response(photo.data, mimetype=photo.content_type)


@app.route('/jobs/<int:job_id>/photos/<int:photo_id>', methods=['DELETE'])
@require_login
def delete_photo(job_id, photo_id):
    job = Job.query.filter_by(id=job_id, user_id=session['user_id']).first_or_404()
    photo = Photo.query.filter_by(id=photo_id, job_id=job.id).first_or_404()
    db.session.delete(photo)
    db.session.commit()
    return jsonify({'message': 'Photo deleted'}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
