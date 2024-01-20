import {
  Cell, Pie, PieChart, ResponsiveContainer, LabelList
} from "recharts";
import {PureComponent} from "react";
import {render} from "react-dom";


const COLORS = ['#86b6f6', '#92c7cf', '#b799ff'];
const RADIAN = Math.PI / 180;

const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent, index, name }) => {
  const labelMappings = {
    'FRONT_BEND': 'Bending',
    'ARMS_UP': 'Arms',
    'FALL': "Fall"
  };

  const displayName = labelMappings[name] || name;

  if (percent === 0) {
    return null;
  }

  const radius = outerRadius + 20;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);

  return (
      <text x={x} y={y} fill="black" textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central">
        {`${displayName}: ${(percent * 100).toFixed(0)}%`}
      </text>
  );
};
export default class PieChartComponent extends PureComponent {

  render() {
    const {data} = this.props;

    return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '35vh'}}>
          <PieChart width={400} height={400}>
            <Pie
                data={data}
                cx="50%"
                cy="50%"
                label={renderCustomizedLabel}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
            >
              {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </div>
    );
  }
}
