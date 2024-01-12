import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  CartesianGrid,
  Tooltip,Legend,
} from 'recharts';

const AreaChartComponent = ({ data, keysAndColors  }) => {
  console.log(data)
  return (
      <ResponsiveContainer width='100%' height={300}>
        <AreaChart data={data} margin={{ top: 50 }}>
          <CartesianGrid strokeDasharray='3 3' />
          <XAxis dataKey='date' />
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