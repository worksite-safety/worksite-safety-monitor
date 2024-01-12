import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  CartesianGrid,
  Tooltip, Legend, Label, YAxis,
} from 'recharts';

const AreaChartComponent = ({ data, keysAndColors, yAxisTitle }) => {
  console.log(data)
  return (
      <ResponsiveContainer width='100%' height={300}>
        <AreaChart data={data} margin={{ top: 50 }}>
          <CartesianGrid strokeDasharray='3 3' />
          <XAxis dataKey='date' />
          <YAxis type='number' allowDecimals={false}>
            <Label
                angle={-90}
                position='insideLeft'
                style={{ textAnchor: 'middle', fontSize: '14px', fontWeight: 'bold'}}
            >
              {yAxisTitle}
            </Label>
          </YAxis>
          <Tooltip />
          <Legend />
          {keysAndColors.map((keyAndColor, index) => (
              <Area
                  key={index}
                  type='monotone'
                  dataKey={keyAndColor.key}
                  stroke={keyAndColor.stroke}
                  fill={keyAndColor.fill}
                  strokeDasharray={keyAndColor.strokeDasharray}
              />
          ))}
        </AreaChart>
      </ResponsiveContainer>
  );
};
export default AreaChartComponent;