import { Link } from 'react-router-dom';
import { Checkmark } from '@carbon/icons-react';

interface Props {
  projectId: string;
  currentStep: 1 | 2 | 3 | 4;
  /** Steps that have been completed (so they become clickable links) */
  completedSteps?: number[];
}

const STEPS = [
  { num: 1, label: 'Upload',    path: (id: string) => `/projects/${id}/upload` },
  { num: 2, label: 'Normalize', path: (id: string) => `/projects/${id}/normalize` },
  { num: 3, label: 'Review',    path: (id: string) => `/projects/${id}/review` },
  { num: 4, label: 'Export',    path: (id: string) => `/projects/${id}/export` },
];

export default function StepProgress({ projectId, currentStep, completedSteps = [] }: Props) {
  return (
    <div className="step-progress">
      <div className="step-progress-inner">
        {STEPS.map(step => {
          const isActive   = step.num === currentStep;
          const isComplete = completedSteps.includes(step.num);
          const isLocked   = !isActive && !isComplete;

          const className = [
            'step-progress-item',
            isActive   ? 'sp-active'   : '',
            isComplete ? 'sp-complete' : '',
            isLocked   ? 'sp-locked'   : '',
          ].filter(Boolean).join(' ');

          const inner = (
            <>
              <span className="step-circle">
                {isComplete ? <Checkmark size={12} /> : step.num}
              </span>
              {step.label}
            </>
          );

          if (isComplete) {
            return (
              <Link key={step.num} to={step.path(projectId)} className={className}>
                {inner}
              </Link>
            );
          }

          return (
            <span key={step.num} className={className}>
              {inner}
            </span>
          );
        })}
      </div>
    </div>
  );
}
