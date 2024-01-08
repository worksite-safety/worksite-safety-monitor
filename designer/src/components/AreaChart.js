import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip, LineChart, Legend, Line,
} from 'recharts';

const AreaChartComponent = ({ data }) => {
  console.log(data)
  return (
      <ResponsiveContainer width='100%' height={300}>
        <AreaChart data={data} margin={{ top: 50 }}>
          <CartesianGrid strokeDasharray='3 3' />
          <XAxis dataKey='date' />
          <Tooltip />
          <Legend />
          <Area type='monotone' dataKey='fall' stroke='#92C7CF' fill='#B799FF' strokeDasharray="5 5"/>
          <Area type='monotone' dataKey='armsUp' stroke='#AAD7D9' fill='#ACBCFF' strokeDasharray="5 5"/>
          <Area type='monotone' dataKey='frontBending' stroke='#86B6F6' fill='#AEE2FF' strokeDasharray="5 5"/>
        </AreaChart>
      </ResponsiveContainer>
  );
};
export default AreaChartComponent;