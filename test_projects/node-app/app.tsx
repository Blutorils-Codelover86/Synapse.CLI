import React, { useState, useEffect } from 'react';

interface MetricData {
  cpu: number;
  memory: number;
  timestamp: string;
}

const Dashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<MetricData | null>(null);

  useEffect(() => {
    fetch('/api/metrics')
      .then(res => res.json())
      .then(setMetrics);
  }, []);

  return (
    <div className="dashboard">
      <h1>System Metrics</h1>
      {metrics && (
        <div>
          <p>CPU: {metrics.cpu}%</p>
          <p>Memory: {metrics.memory}%</p>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
