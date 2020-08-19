from copy import deepcopy
from datetime import datetime
from pathlib import Path
from shutil import copyfile

import requests as r


API_URL = 'https://covid-19-greece.herokuapp.com'

class DailyTests:
    def __init__(self):
        self.data = []
        self.groups = []
        self.bulks = {}

    def load(self):
        res = r.get(f'{API_URL}/total-tests')
        # TODO: Handle error
        api_data = res.json()['total_tests']
        
        prev = 0
        for d in api_data:
            cumulative_tests = prev if d['tests'] is None else d['tests']
            self.data.append({
                'date': d['date'],
                'daily_tests': cumulative_tests - prev,
                'reported_tests': d['tests'] is not None,
                'cumulative_tests': cumulative_tests,
                'corrected': False,
            })
            prev = cumulative_tests

    def run_corrections(self):
        """
        Handle groups and bulks.

        Get groups (cases where there was one report for multiple
        days). Distribute number of tests on grouped days.
        Gather bulks.
        """
        # June 3-4
        total = None
        for d in self.data:
            if d['date'] == '2020-06-03':
                total = d['daily_tests']
                self.groups.append({
                    'total_tests': total,
                    'from': '2020-06-03',
                    'to': '2020-06-04',
                })
            if d['date'] in ['2020-06-03', '2020-06-04']:
                assert(total is not None)
                d['daily_tests'] = total / 2
                d['corrected'] = True

        # June 5-8
        total = None
        for d in self.data:
            if d['date'] == '2020-06-05':
                total = d['daily_tests']
                self.groups.append({
                    'total_tests': total,
                    'from': '2020-06-05',
                    'to': '2020-06-08',
                })
            if d['date'] in ['2020-06-05', '2020-06-06', '2020-06-07', '2020-06-08']:
                assert(total is not None)
                d['daily_tests'] = total / 4
                d['corrected'] = True

        for d in self.data:
            if d['date'] in ['2020-07-29', '2020-08-03', '2020-08-19']:
                self.bulks[d['date']] = d

    def build_weekly_ma(self):
        # Must be odd
        window_len = 7
        # Half of window
        half = window_len // 2
        mas = half * [None]
        i = half
        while i < len(self.data) - half:
            window = [d['daily_tests'] for d in self.data[i-half : i+half+1]]
            ma = round(sum(window) / window_len)
            mas.append(ma)
            i += 1
        mas.extend(half * [None])
        self.weekly_mas = mas

    def plot(self, save=True):
        """
        Plot the data.

        Arguments
        ---------
        save : bool
            If True the plot will be saved in the `plots/` directory.
        """
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt

        xs = list(range(len(self.data)))
        ys = [d['daily_tests'] for d in self.data]
        dates = [d['date'] for d in self.data]

        fig, ax = plt.subplots(figsize=(20, 10))
        fig.suptitle(f'Ημερήσια τεστ COVID-19 στην Ελλάδα ' \
                f'({dates[0]} έως {dates[-1]})', y=0.93)
        ax.set_title('Πηγή: Υπολογισμός διαφορών από τους αριθμούς ' \
                'συνολικών τεστ των επιδημιολογικών αναφορών του ' \
                'ΕΟΔΥ', fontsize=9)
        bar_container = ax.bar(xs, ys, color='#2283C9')
        ax.set_xticks(xs[::2])
        ax.set_xticklabels(labels=dates[::2], rotation=90)

        # Max bar height excluding bulks
        max_height = max(
            y for y, date in zip(ys, dates)
            if date not in self.bulks
        )

        # Adjust bulk heights
        bulks_to_adjust_keys = [
            date for date, d in self.bulks.items()
            if d['daily_tests'] > max_height
        ]
        bulks_to_adjust_keys.sort(key=lambda date: self.bulks[date]['daily_tests'])
 
        step = 0.2 * max_height
        for idx, date in enumerate(bulks_to_adjust_keys, start=1):
            self.bulks[date]['height'] = max_height + idx * step

        ax.set_ylim([
            1.3 * min(ys),
            max_height + (len(bulks_to_adjust_keys) + 1) * step
        ])

        for idx, rect in enumerate(bar_container):
            if self.data[idx]['corrected']:
                rect.set_visible(False)
                continue

            date = datetime.strptime(dates[idx], '%Y-%m-%d').date()
            if date.weekday() in [0, 6]:
                rect.set_facecolor('#175A8A')

            height = rect.get_height()

            if dates[idx] in bulks_to_adjust_keys:
                bulk = self.bulks[dates[idx]]
                height = bulk['height']
                rect.set_height(height)

                # Create break with parallelogram and lines
                x = rect.get_x()
                w = rect.get_width()
                # 1st step: 1.1, 2nd step: 1.3, etc.
                break_y_off = bulk['height'] / max_height - 0.1
                ax.add_patch(mpatches.Polygon([
                    [x - 0.25, break_y_off * max_height],
                    [x - 0.25, (break_y_off + 0.04) * max_height],
                    [x + w + 0.5, (break_y_off + 0.06) * max_height],
                    [x + w + 0.5, (break_y_off + 0.02) * max_height],
                ], color='w', clip_on=False))
                ax.plot(*zip(
                    [x - 0.25, break_y_off * max_height],
                    [x + w + 0.5, (break_y_off + 0.02) * max_height],
                ), color='k')
                ax.plot(*zip(
                    [x - 0.25, (break_y_off + 0.04) * max_height],
                    [x + w + 0.5, (break_y_off + 0.06) * max_height],
                ), color='k')

            if dates[idx] in self.bulks:
                rect.set_facecolor('#E4E4F4')
                rect.set_edgecolor('#888898')
                rect.set_hatch('//////')

            text_y = height + 0.01 * max_height
            rotation = 90 if ys[idx] >= 0 else 0
            if ys[idx] < 0:
                text_y -= 1200
            ax.text(rect.get_x() + 2 * rect.get_width() / 3.0,
                    text_y, ys[idx], ha='center', va='bottom',
                    fontsize=6, rotation=rotation)

        # Groups plot
        date_to_idx = dict(zip(dates, xs))
        for g in self.groups:
            xstart = date_to_idx[g['from']]
            xend = date_to_idx[g['to']]
            xmid = (xstart + xend) / 2
            xlen = xend - xstart + 1
            height = g['total_tests'] / xlen
            width = xlen - 0.2 # margin
            ax.bar([xmid], height, width=width, facecolor='#B1D7F2',
                    edgecolor='#1F78B7', hatch='\\\\')

            text_y = height + 0.01 * max_height
            rotation = 90 if height >= 0 else 0
            if height < 0:
                text_y -= 350
            ax.text(xmid, text_y, g['total_tests'], ha='center',
                    va='bottom', fontsize=6, rotation=rotation)

        # Moving average plot
        ax.plot(xs, self.weekly_mas, '#FFA500', linewidth=3)

        normal_patch = mpatches.Patch(color='#2283C9',
                label='Κανονικές ημέρες')
        weekend_patch = mpatches.Patch(color='#175A8A',
                label='Σάββατο 15:00-Δευτέρα 15:00 (μειωμένοι ' \
                'έλεγχοι στα ΣΚ)')
        grouped_patch = mpatches.Patch(facecolor='#B1D7F2',
                edgecolor='#1F78B7', hatch='\\\\\\',
                label='Ομαδοποιημένες ημέρες (πχ. 5-8 Ιουνίου)')
        special_patch = mpatches.Patch(facecolor='#E4E4F4',
                edgecolor='#888898', hatch='///////',
                label='Μαζική ενσωμάτωση δεδομένων από εργαστήρια')
        ma_patch = mpatches.Patch(facecolor='#FFA500',
                label='Κινητός μέσος όρος 7 ημερών')
        ax.legend(handles=[
            normal_patch, weekend_patch, grouped_patch, special_patch,
            ma_patch,
        ], loc='upper left')

        plt.show()

        # Save
        if save:
            plot_dir = Path('plots')
            plot_dir.mkdir(exist_ok=True)
            plot_filename = f'covid19-el-tests-{dates[-1]}.png'
            fig.savefig(plot_dir / plot_filename)
            # Update latest plot to use this
            copyfile(plot_dir / plot_filename, plot_dir / 'latest.png')


if __name__ == '__main__':
    dt = DailyTests()
    dt.load()
    dt.run_corrections()
    dt.build_weekly_ma()
    dt.plot()

