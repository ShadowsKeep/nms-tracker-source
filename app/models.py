from datetime import datetime, timezone
from app import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Inventory(db.Model):
    """How much of an item the traveller currently owns."""
    __tablename__ = 'inventory'
    item_id = db.Column(db.String(40), primary_key=True)
    have = db.Column(db.Integer, nullable=False, default=0)


class Goal(db.Model):
    """Something the traveller wants to build or stockpile."""
    __tablename__ = 'goals'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.String(40), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(300), nullable=True)
    done = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class Ship(db.Model):
    __tablename__ = 'ships'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(40), nullable=True)      # Fighter, Hauler, ...
    ship_class = db.Column(db.String(2), nullable=True)  # C / B / A / S
    location = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # '<save path>#<hangar index>' when this ship was imported from a save file
    save_key = db.Column(db.String(400), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    repairs = db.relationship('Repair', backref='ship', lazy=True, cascade='all, delete-orphan',
                              order_by='Repair.id')

    # Counted in damaged slots, so "4x Rusted Circuits" is four repairs.
    @property
    def total(self):
        return sum(r.qty for r in self.repairs)

    @property
    def fixed(self):
        return sum(min(r.fixed or 0, r.qty) for r in self.repairs)

    @property
    def percent(self):
        return round(self.fixed / self.total * 100) if self.total else 0


class Repair(db.Model):
    """One broken component on a ship."""
    __tablename__ = 'repairs'
    id = db.Column(db.Integer, primary_key=True)
    ship_id = db.Column(db.Integer, db.ForeignKey('ships.id'), nullable=False)
    item_id = db.Column(db.String(40), nullable=False)   # the damaged component / technology
    qty = db.Column(db.Integer, nullable=False, default=1)      # damaged slots of this kind
    fixed = db.Column(db.Integer, nullable=False, default=0)    # how many of them are repaired
    done = db.Column(db.Boolean, nullable=False, default=False)  # kept equal to fixed >= qty
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    @property
    def remaining(self):
        return max(0, self.qty - (self.fixed or 0))

    def set_fixed(self, value: int):
        self.fixed = max(0, min(int(value), self.qty))
        self.done = self.fixed >= self.qty


class Setting(db.Model):
    """Small key/value store (JSON text), e.g. the live-sync configuration."""
    __tablename__ = 'settings'
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text, nullable=False, default='')
