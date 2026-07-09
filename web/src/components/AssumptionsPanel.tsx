import { Modal } from '@carbon/react';
import { Assumption } from '../api/client';

interface Props {
  open: boolean;
  onClose: () => void;
  vmName: string;
  assumptions: Assumption[];
}

const groups: Array<{ level: Assumption['confidence']; label: string; description: string }> = [
  { level: 'high',   label: 'Mapped directly',  description: 'Value came from customer data — mapped or unit-converted' },
  { level: 'medium', label: 'Inferred',          description: 'Value inferred from other customer fields or naming patterns' },
  { level: 'low',    label: 'IBM defaults',      description: 'No customer data available — standard IBM default applied' },
];

export default function AssumptionsPanel({ open, onClose, vmName, assumptions }: Props) {
  const byLevel = groups.reduce((acc, g) => {
    acc[g.level] = assumptions.filter(a => a.confidence === g.level);
    return acc;
  }, {} as Record<string, Assumption[]>);

  const totalCount = assumptions.length;

  return (
    <Modal
      open={open}
      modalHeading={vmName}
      secondaryButtonText="Close"
      onRequestClose={onClose}
      onSecondarySubmit={onClose}
      size="lg"
      passiveModal={false}
      primaryButtonText=""
    >
      <p style={{ color: '#6f6f6f', fontSize: '0.875rem', marginBottom: '1.5rem', marginTop: '-0.5rem' }}>
        {totalCount} AI decision{totalCount !== 1 ? 's' : ''} made while normalizing this record
      </p>

      {totalCount === 0 && (
        <p style={{ color: '#6f6f6f' }}>No assumptions recorded — all values came directly from customer data.</p>
      )}

      {groups.map(({ level, label, description }) => {
        const items = byLevel[level];
        if (!items?.length) return null;
        return (
          <div key={level}>
            <div className="confidence-section-header">
              <span className={`confidence-dot ${level}`} />
              {label}
              <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, color: '#8d8d8d', marginLeft: '0.25rem' }}>
                — {description}
              </span>
              <span style={{ marginLeft: 'auto', fontWeight: 700, color: '#161616' }}>{items.length}</span>
            </div>

            {items.map((a, idx) => (
              <div key={a.id ?? idx} className={`assumption-item confidence-${level}`}>
                <div className="assumption-field-name">{a.field_name}</div>

                <div className="assumption-values">
                  <div>
                    <span className="assumption-value-label">Used</span>
                    <span className="assumption-value-text">{String(a.assumed_value ?? '—')}</span>
                  </div>
                  {a.original_value != null && a.original_value !== '' && (
                    <div>
                      <span className="assumption-value-label">Customer provided</span>
                      <span className="assumption-value-text" style={{ color: '#6f6f6f' }}>{String(a.original_value)}</span>
                    </div>
                  )}
                </div>

                {a.reasoning && (
                  <p className="assumption-reasoning">{a.reasoning}</p>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </Modal>
  );
}
