import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from 'recharts';

const AreaChartComponent = ({ data }) => {
    return (
        <ResponsiveContainer width='100%' height={300}>
            <AreaChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='3 3' />
                <XAxis dataKey='date' />
                <YAxis type='number' allowDecimals={false} />
                <Tooltip />
                <Area type='monotone' dataKey='fall' stroke='#92C7CF' fill='#3b82f6' />
                <Area type='monotone' dataKey='arms-up' stroke='#AAD7D9' fill='#3b82f6' />
                <Area type='monotone' dataKey='front-bend' stroke='#86B6F6' fill='#3b82f6' />

            </AreaChart>
        </ResponsiveContainer>
    );
};
export default AreaChartComponent;