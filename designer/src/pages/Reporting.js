import * as React from 'react';
import { DataGrid, GridToolbar, GridToolbarFilterButton } from '@mui/x-data-grid';

const VISIBLE_FIELDS = ['eventType', 'startTime', 'timePeriod', 'cameraName'];

export default function ControlledSort() {
    const [rows, setRows] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [sortModel, setSortModel] = React.useState([
        {
            field: 'startTime',
            sort: 'desc',
        },
    ]);

    React.useEffect(() => {
        const fetchCountableEventsData = async (startDate, endDate) => {
            setLoading(true);
            try {
                const response = await fetch(`http://localhost:8080/event/all-events`);
                const jsonData = await response.json();

                // Convert epoch time to human-readable format and handle zero timePeriod
                const modifiedRows = jsonData.map((row) => ({
                    ...row,
                    startTime: new Date(row.startTime).toLocaleString(),
                    timePeriod: row.timePeriod === 0 ? '-' : row.timePeriod,
                }));

                setRows(modifiedRows);
            } catch (error) {
                // Handle error
            } finally {
                setLoading(false);
            }
        };

        const today = new Date();
        const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

        oneWeekAgo.setHours(0, 0, 1);
        today.setHours(23, 59, 59);

        fetchCountableEventsData(oneWeekAgo.getTime(), today.getTime());
    }, []); // Empty dependency array means this effect runs only once, when the component mounts

    const columns = VISIBLE_FIELDS.map((field) => ({ field, headerName: field, flex: 1 }));

    return (
        <div style={{ height: 500, width: '100%' }}>
            <DataGrid
                rows={rows}
                columns={columns}
                loading={loading}
                sortModel={sortModel}
                onSortModelChange={(newSortModel) => setSortModel(newSortModel)}
                components={{
                    Toolbar: () => (
                        <React.Fragment>
                            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                <GridToolbarFilterButton />
                            </div>
                            <GridToolbar />
                        </React.Fragment>
                    ),
                }}
            />
        </div>
    );
}
