import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts';

const BarChartComponent = ({ data }) => {
    return (
        <ResponsiveContainer width='100%' height={300}>
            <BarChart data={data} margin={{ top: 50 }}>
                <CartesianGrid strokeDasharray='10 10 ' />
                <XAxis dataKey='date' />
                <YAxis type='number' allowDecimals={false} />
                <Tooltip />
                <Bar dataKey='fall' fill='#B799FF' barSize={75} />
                <Bar dataKey='armsUp' fill='#ACBCFF' barSize={75} />
                <Bar dataKey='frontBending' fill='#AEE2FF' barSize={75} />
            </BarChart>
        </ResponsiveContainer>
    );
};
export default BarChartComponent;