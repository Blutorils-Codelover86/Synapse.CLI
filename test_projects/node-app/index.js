const express = require('express');
const app = express();

app.get('/api/metrics', (req, res) => {
  res.json({ cpu: 45.2, memory: 67.8 });
});

app.listen(3000, () => {
  console.log('Dashboard server running on port 3000');
});
